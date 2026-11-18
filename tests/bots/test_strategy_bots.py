"""The V2.0 strategy bots: Shark and Adaptive."""

import random

import pytest
from backend.bots.push_fold_solutions import HEADS_UP_RANGES, THREE_HANDED_RANGES

from backend.application.controllers import (
    DecisionContext,
    GameFormat,
    PlayerController,
    build_decision_context,
)
from backend.application.game import PokerGame
from backend.application.ranges import HandRange
from backend.bots.factory import create_bot, get_bot_type
from backend.bots.monte_carlo import deal_showdowns, equity
from backend.bots.opponent_model import (
    PRIOR,
    OpponentRange,
    StatsBook,
    bluff_weight,
    starting_range,
)
from backend.bots.preflop_charts import (
    OPEN_RANGES,
    call_percent,
    open_percent,
    open_range,
    players_behind,
    three_bet_percent,
)
from backend.bots.random_bot import RandomBot
from backend.bots.strategy_bot import StrategyBot, ante_kind, m_ratio
from backend.bots.three_handed_solver import Spot
from backend.poker_engine.actions import Action
from backend.poker_engine.betting import apply_action
from backend.poker_engine.blinds import AnteType, BlindLevel
from backend.poker_engine.constants import ActionType, Card, Position
from backend.poker_engine.hand import advance_hand, start_hand
from backend.poker_engine.models import Hand
from backend.poker_engine.session import GameConfig, create_session
from backend.simulation.config import SeatSpec, SimulationConfig
from backend.simulation.runner import run_simulation
from tests.bots.test_bots import LegalityCheckingController, play_session

SIX_MAX = ["Hero", "SB", "BB", "UTG", "HJ", "CO"]


def shark(adaptive: bool = False) -> StrategyBot:
    return StrategyBot(random.Random(0), adaptive=adaptive)


def act(hand: Hand, name: str, action: ActionType, amount: int | None = None) -> None:
    assert hand.current_player is not None and hand.current_player.name == name
    apply_action(hand, Action(type=action, amount=amount))


def six_max_hand(dealer: int = 0) -> tuple[Hand, list[str]]:
    """A 6-max hand at 5/10; ``dealer`` is the index of the button."""
    session = create_session(player_names=SIX_MAX, config=GameConfig())
    session.table.dealer_index = dealer
    hand = start_hand(session)

    return hand, SIX_MAX


def hero_context(
    hand: Hand,
    cards: tuple[Card, Card],
    game_format: GameFormat = GameFormat.CASH,
    name: str = "Hero",
) -> DecisionContext:
    hero = next(p for p in hand.table.players if p.name == name)
    hero.hand[:] = list(cards)
    assert hand.current_player is hero

    assert hand.blind_level is not None
    big_blind = hand.blind_level.big_blind

    return build_decision_context(hand, hero, big_blind, game_format=game_format)


def decide(context: DecisionContext, adaptive: bool = False) -> Action:
    return shark(adaptive).choose_action(context)


# --- Factory -----------------------------------------------------------------------


def test_the_strategy_bots_are_registered() -> None:
    rng = random.Random(0)
    shark_bot = create_bot("shark", rng)
    adaptive_bot = create_bot("adaptive", rng)

    assert isinstance(shark_bot, StrategyBot) and not shark_bot.adaptive
    assert isinstance(adaptive_bot, StrategyBot) and adaptive_bot.adaptive
    assert isinstance(create_bot("random", rng), RandomBot)


def test_the_strategy_bots_have_no_profile_parameters() -> None:
    with pytest.raises(ValueError, match="no parameters"):
        get_bot_type("shark").build_profile((("bluff_probability", 0.1),))


# --- Pre-flop charts ---------------------------------------------------------------


def test_opening_ranges_widen_with_fewer_players_behind() -> None:
    shares = [open_percent(behind) for behind in sorted(OPEN_RANGES, reverse=True)]

    assert shares == sorted(shares)
    assert shares[0] < 11 < 40 < shares[-1]
    assert open_percent(1, heads_up=True) > 70

    for behind in OPEN_RANGES:
        assert {"AA", "KK", "AKs"} <= open_range(behind).labels


def test_players_behind_follow_the_preflop_order() -> None:
    six = (
        Position.BTN,
        Position.SB,
        Position.BB,
        Position.UTG,
        Position.HJ,
        Position.CO,
    )

    assert players_behind(Position.UTG, six) == 5
    assert players_behind(Position.BTN, six) == 2
    assert players_behind(Position.SB, six) == 1
    assert players_behind(Position.BB, six) == 0
    assert players_behind(Position.BTN, (Position.BTN, Position.BB)) == 1


def test_wider_openers_are_answered_wider() -> None:
    assert three_bet_percent(45) > three_bet_percent(10)
    assert call_percent(45, big_blind=True) > call_percent(45, big_blind=False)


def test_under_the_gun_opens_aces_and_folds_seven_deuce() -> None:
    hand, _ = six_max_hand(dealer=3)  # Hero is under the gun.

    aces = decide(hero_context(hand, ("AS", "AH")))
    trash = decide(hero_context(hand, ("7S", "2H")))

    assert aces.type == ActionType.RAISE and aces.amount == 25
    assert trash.type == ActionType.FOLD


def test_the_button_steals_wider_than_under_the_gun() -> None:
    hand, _ = six_max_hand(dealer=0)

    for name in ("UTG", "HJ", "CO"):
        act(hand, name, ActionType.FOLD)

    assert decide(hero_context(hand, ("KS", "9H"))).type == ActionType.RAISE

    early, _ = six_max_hand(dealer=3)
    assert decide(hero_context(early, ("KS", "9H"))).type == ActionType.FOLD


def test_a_raise_is_reraised_with_aces_and_folded_with_trash() -> None:
    hand, _ = six_max_hand(dealer=0)
    act(hand, "UTG", ActionType.RAISE, 25)
    act(hand, "HJ", ActionType.FOLD)
    act(hand, "CO", ActionType.FOLD)

    three_bet = decide(hero_context(hand, ("AS", "AH")))

    assert three_bet.type == ActionType.RAISE and three_bet.amount == 75
    assert decide(hero_context(hand, ("8S", "3H"))).type == ActionType.FOLD


def test_the_big_blind_checks_a_weak_hand_when_limped_to() -> None:
    hand, _ = six_max_hand(dealer=4)  # Hero is the big blind.

    while hand.current_player is not None and hand.current_player.name != "Hero":
        name = hand.current_player.name
        act(hand, name, ActionType.CALL if name in ("SB", "CO") else ActionType.FOLD)

    assert decide(hero_context(hand, ("7S", "2H"))).type == ActionType.CHECK


# --- Tournaments: M ratio and heads-up push/fold --------------------------------


def heads_up_tournament_spot(
    stack_big_blinds: int, cards: tuple[Card, Card], shove: bool = False
) -> DecisionContext:
    """Heads-up at 50/100; Hero is the small blind (button), or the big
    blind facing a shove when ``shove``."""
    session = create_session(["Hero", "Villain"], GameConfig(starting_stack=10_000))
    session.set_blind_level(BlindLevel(small_blind=50, big_blind=100))
    session.table.dealer_index = 1 if shove else 0

    for player in session.players:
        player.stack = stack_big_blinds * 100

    hand = start_hand(session)

    if shove:
        act(hand, "Villain", ActionType.ALL_IN)

    hero = session.players[0]
    hero.hand[:] = list(cards)

    return build_decision_context(
        hand, hero, big_blind=100, game_format=GameFormat.TOURNAMENT
    )


def test_heads_up_short_stacks_play_the_solved_ranges() -> None:
    push, call = (HandRange.parse(n).labels for n in HEADS_UP_RANGES["none"][10])
    assert "K2o" in push and "72o" not in push

    assert decide(heads_up_tournament_spot(10, ("KS", "2H"))).type == ActionType.ALL_IN
    assert decide(heads_up_tournament_spot(10, ("7S", "2H"))).type == ActionType.FOLD
    assert decide(heads_up_tournament_spot(10, ("AS", "7H"), shove=True)).type in (
        ActionType.CALL,
        ActionType.ALL_IN,
    )
    assert decide(heads_up_tournament_spot(10, ("8S", "3H"), shove=True)).type == (
        ActionType.FOLD
    )


def test_the_solved_ranges_match_the_known_equilibrium() -> None:
    """Published heads-up Nash charts (no ante): about 58% of hands shoved
    and 37% called at 10 big blinds; the ranges narrow as stacks grow."""
    push, call = (HandRange.parse(n).share for n in HEADS_UP_RANGES["none"][10])

    assert 0.54 < push < 0.62
    assert 0.33 < call < 0.42

    pushes = [
        HandRange.parse(HEADS_UP_RANGES["none"][d][0]).share
        for d in sorted(HEADS_UP_RANGES["none"])
    ]
    calls = [
        HandRange.parse(HEADS_UP_RANGES["none"][d][1]).share
        for d in sorted(HEADS_UP_RANGES["none"])
    ]

    assert pushes == sorted(pushes, reverse=True)
    assert calls == sorted(calls, reverse=True)
    assert pushes[0] == calls[0] == 1.0  # At 1 big blind, every hand goes in.


def three_handed_spot(
    stack_big_blinds: int, cards: tuple[Card, Card], ante: int = 0
) -> DecisionContext:
    """Three players at 50/100 (a big-blind ante if ``ante``): Hero is the
    button and acts first."""
    session = create_session(["Hero", "SB", "BB"], GameConfig(starting_stack=10_000))
    session.set_blind_level(
        BlindLevel(
            small_blind=50, big_blind=100, ante=ante, ante_type=AnteType.BIG_BLIND
        )
    )
    session.table.dealer_index = 0

    for player in session.players:
        player.stack = stack_big_blinds * 100

    hand = start_hand(session)

    return hero_context(hand, cards, GameFormat.TOURNAMENT)


def test_three_handed_short_stacks_play_the_solved_ranges() -> None:
    push = HandRange.parse(THREE_HANDED_RANGES["none"][10][Spot.BUTTON_SHOVES]).labels
    shoved = next(label for label in ("A7o", "K9s", "QJs", "77") if label in push)
    folded = next(label for label in ("93o", "72o", "52o") if label not in push)

    def cards(label: str) -> tuple[Card, Card]:
        suits = ("S", "S") if label.endswith("s") else ("S", "H")
        return (label[0] + suits[0], label[1] + suits[1])

    assert decide(three_handed_spot(10, cards(shoved))).type == ActionType.ALL_IN
    assert decide(three_handed_spot(10, cards(folded))).type == ActionType.FOLD


def test_the_antes_of_a_hand_are_recognized() -> None:
    assert ante_kind(three_handed_spot(10, ("AS", "KH"))) == "none"
    assert ante_kind(three_handed_spot(10, ("AS", "KH"), ante=100)) == "big_blind"
    assert ante_kind(heads_up_tournament_spot(10, ("AS", "KH"))) == "none"


def test_m_ratio_counts_the_blinds_and_antes() -> None:
    session = create_session(SIX_MAX, GameConfig(starting_stack=3000))
    session.set_blind_level(BlindLevel(small_blind=50, big_blind=100, ante=10))
    session.table.dealer_index = 3  # Hero is under the gun.
    hand = start_hand(session)
    context = hero_context(hand, ("AS", "KH"), GameFormat.TOURNAMENT)

    # 2,990 chips once the ante is in, for a round costing 50 + 100 + 6 × 10.
    assert m_ratio(context) == pytest.approx(2990 / 210)


def test_a_low_m_ratio_shoves_or_folds() -> None:
    session = create_session(SIX_MAX, GameConfig(starting_stack=600))
    session.set_blind_level(BlindLevel(small_blind=50, big_blind=100, ante=10))
    session.table.dealer_index = 3
    hand = start_hand(session)

    assert decide(hero_context(hand, ("AS", "KH"), GameFormat.TOURNAMENT)).type == (
        ActionType.ALL_IN
    )
    assert decide(hero_context(hand, ("7S", "2H"), GameFormat.TOURNAMENT)).type == (
        ActionType.FOLD
    )


# --- After the flop ----------------------------------------------------------------


def postflop_spot(
    board: tuple[Card, ...],
    cards: tuple[Card, Card],
    villain_bet: int | None = None,
) -> DecisionContext:
    """Heads-up at 5/10: Hero (button) raises to 30, Villain calls, then
    every street is checked through until ``board``; there Villain checks,
    or bets ``villain_bet``."""
    session = create_session(["Hero", "Villain"], GameConfig())
    session.table.dealer_index = 0
    hand = start_hand(session)
    act(hand, "Hero", ActionType.RAISE, 30)
    act(hand, "Villain", ActionType.CALL)
    advance_hand(hand)

    while len(hand.community_cards) < len(board):
        act(hand, "Villain", ActionType.CHECK)
        act(hand, "Hero", ActionType.CHECK)
        advance_hand(hand)

    hand.community_cards[:] = list(board)
    villain = session.players[1]
    villain.hand[:] = [card for card in ("2C", "3C", "4C", "5C") if card not in board][
        :2
    ]

    if villain_bet is None:
        act(hand, "Villain", ActionType.CHECK)
    else:
        act(hand, "Villain", ActionType.RAISE, villain_bet)

    return hero_context(hand, cards)


def test_the_nuts_bets_when_checked_to() -> None:
    context = postflop_spot(("AS", "KS", "QS", "7D", "2C"), ("JS", "TS"))

    assert decide(context).type in (ActionType.RAISE, ActionType.ALL_IN)


def test_the_nuts_never_folds_to_a_bet() -> None:
    context = postflop_spot(
        ("AS", "KS", "QS", "7D", "2C"), ("JS", "TS"), villain_bet=60
    )

    assert decide(context).type in (
        ActionType.CALL,
        ActionType.RAISE,
        ActionType.ALL_IN,
    )


def test_air_folds_to_a_big_river_bet() -> None:
    context = postflop_spot(
        ("AS", "KD", "QS", "7D", "8C"), ("3H", "2D"), villain_bet=120
    )

    assert decide(context).type == ActionType.FOLD


def test_the_decisions_are_reproducible() -> None:
    context = postflop_spot(("AS", "KD", "9S", "7D"), ("QH", "QD"), villain_bet=40)

    assert decide(context) == decide(context)


# --- Ranges and Monte Carlo --------------------------------------------------------


def test_a_raise_narrows_a_range_more_than_a_call() -> None:
    hand, _ = six_max_hand(dealer=0)
    act(hand, "UTG", ActionType.RAISE, 25)
    act(hand, "HJ", ActionType.CALL)
    actions = hand.actions

    raiser = starting_range(actions, "UTG", open_percent(5), PRIOR.vpip * 100)
    caller = starting_range(actions, "HJ", open_percent(4), PRIOR.vpip * 100)

    assert len(raiser) < len(caller)
    assert raiser["AA"] == 1.0
    assert caller["AA"] < 1.0  # Aces would have re-raised.
    assert "72o" not in raiser and "72o" not in caller


def test_a_bet_makes_strong_hands_more_likely() -> None:
    board = ("AS", "7D", "2C")
    hands = {"AKs": 1.0, "QJs": 1.0}
    betting = OpponentRange.from_starting_hands(hands, set(board), random.Random(0))
    weights_before = sum(betting.weights)
    betting.narrow(ActionType.RAISE, board, PRIOR)
    aces = sum(
        w
        for c, w in zip(betting.combos, betting.weights, strict=True)
        if c[0][0] == "A"
    )

    assert sum(betting.weights) < weights_before
    assert aces / sum(betting.weights) > 0.7


def test_aggressive_players_are_expected_to_bluff_more() -> None:
    stats = StatsBook()
    assert bluff_weight(stats.tendencies("Maniac")) == bluff_weight(PRIOR)

    passive = PRIOR.__class__(vpip=0.6, pfr=0.02, aggression=0.1, fold_to_bet=0.1)
    wild = PRIOR.__class__(vpip=0.8, pfr=0.6, aggression=6.0, fold_to_bet=0.2)

    assert bluff_weight(wild) > bluff_weight(PRIOR) > bluff_weight(passive)


def test_monte_carlo_equity_against_a_range() -> None:
    weak = OpponentRange.from_starting_hands(
        {"72o": 1.0}, {"AS", "AH"}, random.Random(0)
    )
    showdowns = deal_showdowns(
        ("AS", "AH"), (), [weak], [[0.0] * len(weak.combos)], 2000, random.Random(1)
    )

    assert len(showdowns) == 2000
    assert equity(showdowns) == pytest.approx(0.88, abs=0.03)


# --- Learning ------------------------------------------------------------------------


def test_the_stats_book_counts_public_actions() -> None:
    hand, _ = six_max_hand(dealer=0)
    act(hand, "UTG", ActionType.RAISE, 25)
    act(hand, "HJ", ActionType.FOLD)
    act(hand, "CO", ActionType.CALL)
    act(hand, "Hero", ActionType.FOLD)
    act(hand, "SB", ActionType.FOLD)
    act(hand, "BB", ActionType.FOLD)
    advance_hand(hand)
    act(hand, "UTG", ActionType.CHECK)
    act(hand, "CO", ActionType.RAISE, 30)
    act(hand, "UTG", ActionType.FOLD)

    book = StatsBook()
    book.record_hand(hand.actions)

    utg, co, hj = book.players["UTG"], book.players["CO"], book.players["HJ"]
    assert (utg.hands, utg.vpip_hands, utg.pfr_hands) == (1, 1, 1)
    assert (utg.bets_faced, utg.folds_to_bet) == (1, 1)
    assert (co.vpip_hands, co.pfr_hands, co.aggressive_actions) == (1, 0, 1)
    assert (hj.hands, hj.vpip_hands) == (1, 0)
    assert book.tendencies("UTG").fold_to_bet > PRIOR.fold_to_bet


class Spy(PlayerController):
    """Folds or checks, and counts the hands it is shown."""

    def __init__(self) -> None:
        self.hands: list[int] = []

    def choose_action(self, context: DecisionContext) -> Action:
        legal = {a.type for a in context.legal_actions}
        return Action(
            type=ActionType.CHECK if ActionType.CHECK in legal else ActionType.FOLD
        )

    def observe_hand(self, actions: tuple) -> None:  # type: ignore[override]
        self.hands.append(len(actions))


def test_every_controller_sees_each_finished_hand() -> None:
    spies = {"Alice": Spy(), "Bob": Spy(), "Carol": Spy()}
    session = create_session(list(spies), GameConfig())
    session.table.dealer_index = 0
    game = PokerGame(session, spies)

    for _ in range(3):
        game.start_hand()
        while game.is_hand_in_progress:
            game.step()

    assert all(len(spy.hands) == 3 and all(spy.hands) for spy in spies.values())


def test_only_the_adaptive_bot_learns() -> None:
    hand, _ = six_max_hand(dealer=0)
    act(hand, "UTG", ActionType.RAISE, 25)
    actions = tuple(hand.actions)
    learner, fixed = shark(adaptive=True), shark()

    for _ in range(30):
        learner.observe_hand(actions)
        fixed.observe_hand(actions)

    assert learner.tendencies("UTG").pfr > PRIOR.pfr
    assert fixed.tendencies("UTG") == PRIOR


# --- Whole games -----------------------------------------------------------------------


@pytest.mark.parametrize("bot", ["shark", "adaptive"])
def test_strategy_bots_play_legal_actions_and_keep_the_chips(bot: str) -> None:
    controllers: dict[str, PlayerController] = {
        "Alice": LegalityCheckingController(create_bot(bot, random.Random(1))),
        "Bob": LegalityCheckingController(create_bot(bot, random.Random(2))),
        "Carol": LegalityCheckingController(RandomBot(random.Random(3))),
        "Dave": LegalityCheckingController(create_bot("maniac", random.Random(4))),
    }

    play_session(controllers, max_hands=60)

    assert all(c.decisions for c in controllers.values())  # type: ignore[attr-defined]


def test_the_strategy_bots_beat_the_calling_station() -> None:
    config = SimulationConfig(
        seats=(SeatSpec("shark"), SeatSpec("adaptive"), SeatSpec("station")),
        hands=300,
        seed=7,
    )
    result = run_simulation(config)
    net = {s.bot: s.net_chips for s in result.players.values()}

    assert net["station"] < 0 < min(net["shark"], net["adaptive"])


def test_the_adaptive_bot_opens_wider_with_a_loose_player_behind() -> None:
    hand, _ = six_max_hand(dealer=0)
    act(hand, "UTG", ActionType.RAISE, 25)

    for name in ("HJ", "CO", "Hero", "SB"):
        act(hand, name, ActionType.FOLD)

    act(hand, "BB", ActionType.CALL)  # "BB" plays every hand.
    learner, fixed = shark(adaptive=True), shark()

    for _ in range(40):
        learner.observe_hand(tuple(hand.actions))

    spot, _ = six_max_hand(dealer=3)  # Hero under the gun, "BB" behind.
    context = hero_context(spot, ("KS", "6S"))

    assert "K6s" not in open_range(5).labels and "K6s" in open_range(3).labels
    assert learner.choose_action(context).type == ActionType.RAISE
    assert fixed.choose_action(context).type == ActionType.FOLD
