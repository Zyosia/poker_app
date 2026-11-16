"""Tournaments: complete runs, eliminations, payouts, heads-up, rebuys, Spin & Go."""

import random

import pytest

from backend.application.controllers import DecisionContext, PlayerController
from backend.application.payouts import (
    FAIR_MULTIPLIERS,
    HIGH_MULTIPLIER,
    TOP_THREE,
    Multiplier,
    MultiplierTable,
)
from backend.application.structures import (
    SPIN_HYPER_TURBO,
    SPIN_STARTING_STACK,
    TOURNAMENT_LEVELS,
    TURBO,
    with_classic_antes,
)
from backend.application.tournament import (
    LevelClock,
    RebuyRules,
    SpinConfig,
    Tournament,
    TournamentConfig,
    create_spin,
)
from backend.bots.factory import create_bot
from backend.poker_engine.actions import Action
from backend.poker_engine.blinds import AnteType, BlindStructure
from backend.poker_engine.constants import ActionType, Position
from tests.helpers import stacked_deck

STYLES = ("nit", "tag", "lag", "station", "maniac", "basic")


class Policy(PlayerController):
    """Plays one simple plan: "shove", "call" or "fold" (checks when free)."""

    def __init__(self, plan: str = "fold", is_human: bool = False) -> None:
        self.plan = plan
        self.is_human = is_human

    def choose_action(self, context: DecisionContext) -> Action:
        legal = {action.type for action in context.legal_actions}
        preferences = {
            "shove": (ActionType.ALL_IN, ActionType.CALL, ActionType.CHECK),
            "call": (ActionType.CALL, ActionType.CHECK),
            "fold": (ActionType.CHECK, ActionType.FOLD),
        }[self.plan]

        return Action(type=next(t for t in preferences if t in legal))


def bot_tournament(
    seed: int, players: int = 6, config: TournamentConfig | None = None
) -> Tournament:
    rng = random.Random(seed)
    names = [f"P{index}" for index in range(players)]
    controllers = {
        name: create_bot(STYLES[index], random.Random(rng.getrandbits(32)))
        for index, name in enumerate(names)
    }

    return Tournament(
        config or TournamentConfig(TURBO, starting_stack=1500),
        names,
        controllers,
        dealer_index=seed % players,
        deck_rng=random.Random(seed),
    )


def policy_tournament(
    stacks: dict[str, int],
    plans: dict[str, str],
    config: TournamentConfig,
    human: str | None = None,
) -> tuple[Tournament, dict[str, Policy]]:
    controllers = {
        name: Policy(plans.get(name, "fold"), is_human=name == human) for name in stacks
    }
    tournament = Tournament(config, list(stacks), controllers, dealer_index=0)

    for player in tournament.players:
        player.stack = stacks[player.name]

    return tournament, controllers


def total_chips_expected(tournament: Tournament, starting_stack: int) -> int:
    rules = tournament.config.rebuys
    chips = starting_stack * tournament.entrants

    for name in (player.name for player in tournament.players):
        finish_rebuys = tournament._entries[name].rebuys  # noqa: SLF001
        add_ons = tournament._entries[name].add_ons  # noqa: SLF001

        if rules is not None:
            chips += finish_rebuys * rules.rebuy_stack
            chips += add_ons * (rules.add_on_stack or 0)

    return chips


# --- Complete tournaments ------------------------------------------------


REBUYS = RebuyRules(levels=3, threshold=1500, rebuy_stack=1500, add_on_stack=1500)


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("rebuys", [None, REBUYS], ids=["freezeout", "rebuys"])
def test_complete_tournaments_conserve_chips_and_pay_the_pool(
    seed: int, rebuys: RebuyRules | None
) -> None:
    config = TournamentConfig(TURBO, starting_stack=1500, rebuys=rebuys)
    tournament = bot_tournament(seed, players=2 + seed % 5, config=config)

    while not tournament.is_finished:
        tournament.play_hand()
        chips = sum(player.stack for player in tournament.players)
        assert chips == total_chips_expected(tournament, 1500)

    result = tournament.result
    places = [finish.place for finish in result.finishes]

    assert sum(finish.prize for finish in result.finishes) == result.prize_pool
    assert places == sorted(places) and places[0] == 1
    assert result.winner.eliminated_on_hand is None
    assert result.winner.prize > 0
    assert all(f.eliminated_on_hand for f in result.finishes[1:])
    assert not result.capped
    assert result.level == TURBO.level(result.level_index)


def test_the_same_seed_gives_the_same_tournament() -> None:
    first = bot_tournament(11).play_to_end()
    again = bot_tournament(11).play_to_end()

    assert first == again
    assert first.to_dict() == again.to_dict()


def test_the_blind_level_follows_the_hands_played() -> None:
    tournament = bot_tournament(3)
    levels = []

    while not tournament.is_finished and tournament.hands_played < 13:
        levels.append(tournament.play_hand().blind_level)

    # Turbo: six hands per level.
    assert levels[:6] == [TURBO.level(0)] * 6
    assert levels[6:12] == [TURBO.level(1)] * 6
    assert levels[12] == TURBO.level(2)


def test_classic_antes_are_posted_in_a_tournament() -> None:
    structure = with_classic_antes(TURBO)
    level = structure.level(3)
    assert level.ante_type == AnteType.CLASSIC and level.ante == 10

    tournament = bot_tournament(
        2, config=TournamentConfig(structure, starting_stack=1500, max_hands=40)
    )
    hands = [tournament.play_hand() for _ in range(19)]

    assert any(event.action == "post_ante" for event in hands[18].actions)


def test_a_hand_cap_ranks_the_survivors_by_stack() -> None:
    config = TournamentConfig(TURBO, starting_stack=1500, max_hands=3)
    result = bot_tournament(5, config=config).play_to_end()

    assert result.capped
    assert result.hands_played == 3
    assert sum(finish.prize for finish in result.finishes) == result.prize_pool


# --- Eliminations ----------------------------------------------------------


SHOWDOWN_FOR_A = {
    "hole_cards": {
        "A": ("AS", "AH"),
        "B": ("4C", "5S"),
        "C": ("8C", "8S"),
        "D": ("KC", "QD"),
    },
    "board": ("2D", "7C", "9H", "JS", "3D"),
    # Left of the button (A): B, C, D, then A.
    "order": ("B", "C", "D", "A"),
}


def test_players_busted_together_finish_by_their_starting_stack() -> None:
    stacks = {"A": 3000, "B": 200, "C": 300, "D": 2500}
    config = TournamentConfig(TURBO, starting_stack=1500)
    tournament, _ = policy_tournament(stacks, dict.fromkeys(stacks, "shove"), config)

    tournament.play_hand(stacked_deck(**SHOWDOWN_FOR_A))
    result = tournament.result

    assert [(f.name, f.place) for f in result.finishes] == [
        ("A", 1),
        ("D", 2),
        ("C", 3),
        ("B", 4),
    ]
    # 65 / 35 of four buy-ins of 100.
    assert [f.prize for f in result.finishes] == [260, 140, 0, 0]
    assert [f.eliminated_on_hand for f in result.finishes] == [None, 1, 1, 1]
    assert [(e.names, e.place) for e in tournament.eliminations] == [
        (("D",), 2),
        (("C",), 3),
        (("B",), 4),
    ]


def test_equal_stacks_busted_together_share_their_places() -> None:
    stacks = {"A": 2700, "B": 300, "C": 300, "D": 2700}
    # 4 x 102 = 408: 50/30/20 pays 205 / 122 / 81 / 0.
    config = TournamentConfig(TURBO, starting_stack=1500, buy_in=102, payout=TOP_THREE)
    tournament, _ = policy_tournament(stacks, dict.fromkeys(stacks, "shove"), config)

    tournament.play_hand(stacked_deck(**SHOWDOWN_FOR_A))
    result = tournament.result

    # B and C share 3rd and 4th: 81 + 0, the odd unit to B (first left of
    # the button).
    assert [(f.name, f.place, f.prize) for f in result.finishes] == [
        ("A", 1, 205),
        ("D", 2, 122),
        ("B", 3, 41),
        ("C", 3, 40),
    ]
    assert tournament.eliminations[-1].names == ("B", "C")
    assert tournament.eliminations[-1].prizes == (41, 40)


def test_going_heads_up_follows_the_heads_up_rules() -> None:
    # A shoves, B calls all-in, C folds his big blind: B is out.
    stacks = {"A": 2000, "B": 500, "C": 2000}
    config = TournamentConfig(TURBO, starting_stack=1500)
    tournament, controllers = policy_tournament(
        stacks, {"A": "shove", "B": "shove", "C": "fold"}, config
    )
    deck = stacked_deck(
        hole_cards={"A": ("AS", "AH"), "B": ("4C", "5S"), "C": ("7H", "2S")},
        board=("2D", "7C", "9H", "JS", "3D"),
        order=("B", "C", "A"),
    )

    tournament.play_hand(deck)

    assert not tournament.is_finished
    assert [p.name for p in tournament.players_left()] == ["A", "C"]

    for controller in controllers.values():
        controller.plan = "call"

    hand = tournament.start_hand()
    table = hand.table
    a, c = (next(p for p in table.players if p.name == n) for n in ("A", "C"))

    # The moving button goes from A to C, the next player with chips.
    assert table.dealer is c
    assert c.position == Position.BTN and a.position == Position.BB
    assert [(e.player, e.action) for e in hand.actions[:2]] == [
        ("C", "post_sb"),
        ("A", "post_bb"),
    ]
    assert hand.current_player is c  # The button acts first pre-flop.

    tournament.step()  # C completes.
    tournament.step()  # A checks.
    tournament.step()  # The flop is dealt.

    assert hand.current_player is a  # The button acts last after the flop.


# --- Rebuys and add-on -----------------------------------------------------


REBUY_STRUCTURE = BlindStructure("Test", TOURNAMENT_LEVELS[:4], hands_per_level=1)
BUSTED_ONLY = RebuyRules(levels=2, threshold=0, rebuy_stack=1500, add_on_stack=1000)


def human_busts_in_hand_one() -> Tournament:
    # H shoves into A, B folds: A wins with aces.
    stacks = {"H": 1500, "A": 1500, "B": 1500}
    config = TournamentConfig(REBUY_STRUCTURE, starting_stack=1500, rebuys=BUSTED_ONLY)
    tournament, _ = policy_tournament(
        stacks, {"H": "shove", "A": "shove", "B": "fold"}, config, human="H"
    )
    deck = stacked_deck(
        hole_cards={"A": ("AS", "AH"), "B": ("7H", "2S"), "H": ("4C", "5S")},
        board=("2D", "7C", "9H", "JS", "3D"),
        order=("A", "B", "H"),
    )
    tournament.play_hand(deck)

    return tournament


def test_a_busted_human_may_rebuy_during_the_rebuy_period() -> None:
    tournament = human_busts_in_hand_one()

    assert tournament.is_waiting_for_rebuy
    assert tournament.can_rebuy("H")
    assert tournament.prize_pool == 300

    tournament.rebuy("H")

    assert not tournament.is_waiting_for_rebuy
    assert tournament.players[0].stack == 1500
    assert tournament.prize_pool == 400
    assert tournament.invested("H") == 200


def test_a_declined_rebuy_eliminates_the_player() -> None:
    tournament = human_busts_in_hand_one()

    tournament.decline_rebuy("H")

    assert tournament.current_place("H") == 3
    assert tournament.eliminations[-1].names == ("H",)
    assert not tournament.can_rebuy("H")


def test_starting_the_next_hand_without_rebuying_eliminates_the_player() -> None:
    tournament = human_busts_in_hand_one()

    tournament.start_hand()

    assert tournament.current_place("H") == 3


def test_the_add_on_is_offered_once_at_the_end_of_the_rebuy_period() -> None:
    tournament = human_busts_in_hand_one()
    tournament.rebuy("H")
    assert not tournament.can_add_on("H")

    for controller in tournament.controllers.values():
        assert isinstance(controller, Policy)
        controller.plan = "fold"

    tournament.play_hand()  # Hand 2: the last hand of the rebuy period.

    assert not tournament.rebuy_period_open
    assert tournament.can_add_on("H")
    stack = tournament.players[0].stack
    tournament.add_on("H")
    assert tournament.players[0].stack == stack + 1000

    # Bots at or below the starting stack took it themselves: B folded twice.
    entries = tournament._entries  # noqa: SLF001
    assert entries["B"].add_ons == 1 and entries["A"].add_ons == 0
    assert tournament.prize_pool == 100 * (3 + 1 + 2)
    assert tournament.invested("H") == 300

    tournament.start_hand()
    assert not tournament.can_add_on("H")
    assert not tournament.can_rebuy("B")


def test_bots_rebuy_whenever_they_may() -> None:
    config = TournamentConfig(TURBO, starting_stack=1500, rebuys=REBUYS)
    result = bot_tournament(3, config=config).play_to_end()

    rebuys = sum(finish.rebuys for finish in result.finishes)
    add_ons = sum(finish.add_ons for finish in result.finishes)

    assert rebuys > 0
    assert result.prize_pool == 100 * (6 + rebuys + add_ons)
    assert all(
        finish.invested == 100 * (1 + finish.rebuys + finish.add_ons)
        for finish in result.finishes
    )


# --- Levels by time --------------------------------------------------------


class FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_level_clock_runs_until_paused() -> None:
    fake = FakeTime()
    clock = LevelClock(fake)

    fake.now += 30
    clock.pause()
    fake.now += 100
    assert clock.elapsed() == 30
    assert clock.is_paused

    clock.resume()
    fake.now += 10
    assert clock.elapsed() == 40


def test_levels_by_time_change_between_hands_only() -> None:
    fake = FakeTime()
    rng = random.Random(1)
    names = ["A", "B", "C"]
    tournament = Tournament(
        TournamentConfig(TURBO, starting_stack=1500),
        names,
        {name: create_bot("tag", random.Random(rng.random())) for name in names},
        clock=LevelClock(fake),
        deck_rng=rng,
    )

    tournament.play_hand()
    fake.now += 3 * 60 + 1  # Turbo: 3 minutes per level.
    assert tournament.level_index == 0  # Nothing changes during a hand break.

    hand = tournament.play_hand()

    assert hand.blind_level == TURBO.level(1)
    remaining = tournament.next_level_in()
    assert remaining is not None and remaining == pytest.approx(3 * 60 - 1)


# --- Spin & Go -------------------------------------------------------------


def spin(seed: int, table: MultiplierTable = FAIR_MULTIPLIERS) -> Tournament:
    names = ["X", "Y", "Z"]
    rng = random.Random(seed)
    controllers = {
        name: create_bot(style, random.Random(rng.random()))
        for name, style in zip(names, ("tag", "lag", "maniac"), strict=True)
    }

    return create_spin(SpinConfig(table), names, controllers, random.Random(seed))


@pytest.mark.parametrize("seed", range(5))
def test_a_spin_and_go_ends_with_one_winner_taking_the_multiplied_pool(
    seed: int,
) -> None:
    tournament = spin(seed)
    assert tournament.players[0].stack == SPIN_STARTING_STACK
    assert tournament.level == SPIN_HYPER_TURBO.level(0)

    result = tournament.play_to_end()

    assert result.multiplier is not None
    assert result.prize_pool == result.multiplier * 10
    assert [f.prize for f in result.finishes] == [result.prize_pool, 0, 0]
    assert all(finish.invested == 10 for finish in result.finishes)


def test_a_high_multiplier_pays_three_places() -> None:
    table = MultiplierTable("Only 100x", (Multiplier(100, 1, HIGH_MULTIPLIER),))

    result = spin(1, table).play_to_end()

    assert result.prize_pool == 1000
    assert [f.prize for f in result.finishes] == [800, 100, 100]


def test_the_multiplier_is_drawn_from_the_seed() -> None:
    assert spin(4).multiplier == spin(4).multiplier
    assert spin(4).play_to_end() == spin(4).play_to_end()


# --- Validation ------------------------------------------------------------


def test_invalid_tournaments_are_rejected() -> None:
    bot = Policy()

    with pytest.raises(ValueError):
        Tournament(TournamentConfig(TURBO, 1500), ["A"], {"A": bot})

    with pytest.raises(ValueError):
        Tournament(TournamentConfig(TURBO, 1500), ["A", "A"], {"A": bot})

    with pytest.raises(ValueError):
        Tournament(TournamentConfig(TURBO, 1500), ["A", "B"], {"A": bot})

    with pytest.raises(ValueError):
        TournamentConfig(TURBO, starting_stack=0)

    with pytest.raises(ValueError):
        create_spin(SpinConfig(FAIR_MULTIPLIERS), ["A", "B"], {}, random.Random())
