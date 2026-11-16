"""Stack-aware tournament play: push/fold, short stacks, styles, cash unchanged."""

import random

import pytest

from backend.application.controllers import (
    DecisionContext,
    GameFormat,
    build_decision_context,
)
from backend.bots.basic_bot import BasicBot
from backend.bots.profiles import (
    BASIC_PROFILE,
    CALLING_STATION_PROFILE,
    LAG_PROFILE,
    MANIAC_PROFILE,
    NIT_PROFILE,
    TAG_PROFILE,
    BotProfile,
)
from backend.bots.push_fold import (
    COMBINATIONS,
    HAND_ORDER,
    call_shove_percent,
    combinations,
    hand_class,
    in_top_percent,
    open_shove_percent,
)
from backend.bots.short_stack import effective_big_blinds
from backend.poker_engine.actions import Action
from backend.poker_engine.betting import apply_action
from backend.poker_engine.constants import RANKS, ActionType, Card, Position
from backend.poker_engine.hand import start_hand
from backend.poker_engine.session import GameConfig, create_session

PROFILES: dict[str, BotProfile] = {
    "nit": NIT_PROFILE,
    "tag": TAG_PROFILE,
    "basic": BASIC_PROFILE,
    "station": CALLING_STATION_PROFILE,
    "lag": LAG_PROFILE,
    "maniac": MANIAC_PROFILE,
}
NAMES = ["Hero", "SB", "BB", "UTG", "HJ", "CO"]


def one_combo_per_class() -> dict[str, tuple[Card, Card]]:
    combos: dict[str, tuple[Card, Card]] = {}

    for high_index, high in enumerate(RANKS):
        for low in RANKS[: high_index + 1]:
            if high == low:
                combos[high + low] = (high + "S", low + "H")
            else:
                combos[high + low + "s"] = (high + "S", low + "S")
                combos[high + low + "o"] = (high + "S", low + "H")

    return combos


HANDS = one_combo_per_class()


def button_spot(
    hero_stack: int,
    hole_cards: tuple[Card, Card],
    shove_from: str | None = None,
    game_format: GameFormat = GameFormat.TOURNAMENT,
) -> DecisionContext:
    """Hero on the button of a 6-max table at 5/10, folded to (or shoved to).

    UTG, HJ and CO fold, unless ``shove_from`` names one of them, who then
    shoves 1000 and the others fold.
    """
    session = create_session(player_names=NAMES, config=GameConfig())
    session.table.dealer_index = 0  # Hero is the Button.
    session.players[0].stack = hero_stack
    hand = start_hand(session)

    for name in ("UTG", "HJ", "CO"):
        assert hand.current_player is not None
        assert hand.current_player.name == name
        action = ActionType.ALL_IN if name == shove_from else ActionType.FOLD
        apply_action(hand, Action(type=action))

    hero = session.players[0]
    hero.hand[:] = list(hole_cards)
    assert hand.current_player is hero

    return build_decision_context(hand, hero, big_blind=10, game_format=game_format)


def decide(profile: BotProfile, context: DecisionContext) -> ActionType:
    return BasicBot(random.Random(0), profile).choose_action(context).type


# --- Ranges -------------------------------------------------------------


def test_the_hand_order_lists_every_starting_hand_once() -> None:
    assert len(HAND_ORDER) == 169
    assert set(HAND_ORDER) == set(HANDS)
    assert sum(combinations(hand) for hand in HAND_ORDER) == COMBINATIONS


def test_the_hand_order_starts_with_the_premium_pairs() -> None:
    assert HAND_ORDER[:2] == ("AA", "KK")
    assert HAND_ORDER.index("AKs") < 10
    assert {"32o", "72o"} & set(HAND_ORDER[-6:])


def test_hand_classes() -> None:
    assert hand_class(("KH", "AS")) == "AKo"
    assert hand_class(("5D", "TD")) == "T5s"
    assert hand_class(("9C", "9S")) == "99"


def test_ranges_hold_the_strongest_hands() -> None:
    assert in_top_percent(("AS", "AH"), 0.1)
    assert not in_top_percent(("7S", "2H"), 50)
    assert in_top_percent(("7S", "2H"), 100)


def test_ranges_widen_with_shorter_stacks_and_later_positions() -> None:
    assert open_shove_percent(Position.UTG, 5) > open_shove_percent(Position.UTG, 12)
    assert open_shove_percent(Position.BTN, 10) > open_shove_percent(Position.UTG, 10)
    assert open_shove_percent(Position.SB, 10) > open_shove_percent(Position.BTN, 10)
    # Linear between two columns (10 bb: 15%, 12 bb: 13%).
    assert open_shove_percent(Position.UTG, 11) == pytest.approx(14)
    assert call_shove_percent(True, 10, multiway=False) == 25
    assert call_shove_percent(False, 10, multiway=True) == 7


# --- Push/fold -----------------------------------------------------------


@pytest.mark.parametrize("name", PROFILES)
def test_at_8_big_blinds_every_profile_shoves_or_folds(name: str) -> None:
    for hand, cards in HANDS.items():
        context = button_spot(80, cards)
        assert effective_big_blinds(context) == 8

        action = decide(PROFILES[name], context)

        assert action in (ActionType.ALL_IN, ActionType.FOLD), (name, hand, action)


@pytest.mark.parametrize("name", PROFILES)
@pytest.mark.parametrize("pair", ["AA", "KK"])
def test_premium_pairs_always_shove_short(name: str, pair: str) -> None:
    for stack in (30, 80, 120):
        assert decide(PROFILES[name], button_spot(stack, HANDS[pair])) == (
            ActionType.ALL_IN
        )


@pytest.mark.parametrize("name", PROFILES)
def test_a_shove_is_called_all_in_or_folded(name: str) -> None:
    for hand, cards in HANDS.items():
        action = decide(PROFILES[name], button_spot(80, cards, shove_from="UTG"))

        assert action in (ActionType.ALL_IN, ActionType.CALL, ActionType.FOLD)

        if hand in ("AA", "KK"):
            assert action != ActionType.FOLD


def shoving_share(profile: BotProfile, stack: int) -> float:
    shoved = sum(
        combinations(hand)
        for hand, cards in HANDS.items()
        if decide(profile, button_spot(stack, cards)) == ActionType.ALL_IN
    )

    return shoved / COMBINATIONS


def test_the_profiles_keep_their_order() -> None:
    shares = [
        shoving_share(PROFILES[name], 80) for name in ("nit", "tag", "lag", "maniac")
    ]

    assert shares == sorted(shares)
    assert len(set(shares)) == 4  # Nit tightest, Maniac loosest.


def test_the_calling_station_calls_shoves_widest() -> None:
    def calling_share(profile: BotProfile) -> int:
        return sum(
            combinations(hand)
            for hand, cards in HANDS.items()
            if decide(profile, button_spot(80, cards, "UTG")) != ActionType.FOLD
        )

    station = calling_share(CALLING_STATION_PROFILE)

    assert station > calling_share(TAG_PROFILE) > calling_share(NIT_PROFILE)


# --- Short stacks --------------------------------------------------------


def test_a_short_stack_opens_small() -> None:
    action = BasicBot(random.Random(0), TAG_PROFILE).choose_action(
        button_spot(200, HANDS["AA"])
    )

    # 20 big blinds: 2.2 big blinds, not a pot-sized raise.
    assert action == Action(type=ActionType.RAISE, amount=22)


def test_a_short_stack_reshoves_instead_of_flat_calling() -> None:
    session = create_session(player_names=NAMES, config=GameConfig())
    session.table.dealer_index = 0
    session.players[0].stack = 200
    hand = start_hand(session)
    apply_action(hand, Action(type=ActionType.RAISE, amount=25))  # UTG opens.
    apply_action(hand, Action(type=ActionType.FOLD))
    apply_action(hand, Action(type=ActionType.FOLD))
    hero = session.players[0]
    hero.hand[:] = ["KS", "KH"]
    context = build_decision_context(hand, hero, 10, GameFormat.TOURNAMENT)

    assert BasicBot(random.Random(0), TAG_PROFILE).choose_action(context) == Action(
        type=ActionType.ALL_IN
    )


def test_deep_stacks_play_the_usual_heuristic_in_tournaments() -> None:
    deep = button_spot(1000, HANDS["AA"])

    tournament = BasicBot(random.Random(5), TAG_PROFILE).choose_action(deep)
    cash = BasicBot(random.Random(5), TAG_PROFILE).choose_action(
        button_spot(1000, HANDS["AA"], game_format=GameFormat.CASH)
    )

    assert tournament == cash


@pytest.mark.parametrize("name", PROFILES)
def test_cash_games_ignore_the_stack_depth(name: str) -> None:
    # Same decision as the heuristic, even at 8 big blinds: cash is unchanged.
    for cards in list(HANDS.values())[::7]:
        context = button_spot(80, cards, game_format=GameFormat.CASH)
        bot = BasicBot(random.Random(9), PROFILES[name])
        reference = BasicBot(random.Random(9), PROFILES[name])

        assert bot.choose_action(context) == reference._heuristic_action(context)  # noqa: SLF001


def test_invalid_short_stack_parameters_are_rejected() -> None:
    with pytest.raises(ValueError):
        BotProfile(shove_range_scale=0)

    with pytest.raises(ValueError):
        BotProfile(push_fold_big_blinds=20, short_stack_big_blinds=15)
