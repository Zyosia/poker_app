"""Pot Limit, Fixed Limit and the betting cap (V3.1.1).

Every hand is dealt by ``start_hand``: the blinds are posted as in a real
hand. Alice (index 0) is the Button, Bob the Small Blind and Charlie the Big
Blind, so Alice acts first pre-flop and Bob first after the flop.
"""

import random

import pytest

from backend.poker_engine.actions import LegalAction
from backend.poker_engine.betting import (
    IllegalActionError,
    apply_action,
    get_current_legal_actions,
)
from backend.poker_engine.constants import (
    FIXED_LIMIT_BET_CAP,
    ActionType,
    BettingRules,
    BettingStructure,
)
from backend.poker_engine.deck import Deck
from backend.poker_engine.hand import advance_hand, start_hand
from backend.poker_engine.models import Hand
from backend.poker_engine.session import GameConfig, GameSession, create_session
from tests.helpers import to_action

NL = BettingStructure.NO_LIMIT
PL = BettingStructure.POT_LIMIT
FL = BettingStructure.FIXED_LIMIT


def deal(
    structure: BettingStructure,
    stacks: tuple[int, int, int] = (1000, 1000, 1000),
    bet_cap: int | None = None,
) -> tuple[GameSession, Hand]:
    session = create_session(
        ["Alice", "Bob", "Charlie"],
        GameConfig(
            small_blind=5,
            big_blind=10,
            betting=BettingRules(structure, bet_cap),
        ),
    )
    session.table.dealer_index = 0

    for player, stack in zip(session.players, stacks, strict=True):
        player.stack = stack

    hand = start_hand(session, deck=Deck(random.Random(7)))
    alice = session.players[0]
    assert hand.first_to_act is alice

    return session, hand


def act(hand: Hand, *specs: tuple[str, int | None]) -> None:
    for spec in specs:
        apply_action(hand, to_action(spec))


def legal(hand: Hand) -> dict[str, LegalAction]:
    return {action.type: action for action in get_current_legal_actions(hand)}


def raise_range(hand: Hand) -> tuple[int | None, int | None]:
    action = legal(hand)[ActionType.RAISE]

    return action.min_amount, action.max_amount


def to_flop(hand: Hand) -> None:
    """Everyone calls the big blind: the flop comes, with a pot of 30."""
    act(hand, ("call", None), ("call", None), ("check", None))
    advance_hand(hand)
    assert hand.pot == 30


# --- The configuration --------------------------------------------------------


def test_fixed_limit_is_capped_at_four_bets_unless_set_otherwise() -> None:
    assert GameConfig().betting == BettingRules(NL, None)
    assert BettingRules().table_cap is None
    assert BettingRules(PL).table_cap is None
    assert BettingRules(FL).table_cap == FIXED_LIMIT_BET_CAP == 4
    assert BettingRules(FL, 6).table_cap == 6
    assert BettingRules(NL, 3).table_cap == 3


def test_a_cap_must_allow_a_bet_and_a_raise() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        BettingRules(NL, 1)


def test_the_hand_plays_with_the_session_structure() -> None:
    _, hand = deal(FL, bet_cap=5)

    assert (hand.betting, hand.bet_cap) == (FL, 5)
    assert (hand.bets_this_street, hand.full_bet) == (1, 10)  # The big blind.


# --- Pot Limit ----------------------------------------------------------------


def test_pot_limit_first_raise_is_to_three_and_a_half_big_blinds() -> None:
    _, hand = deal(PL)

    # Call 10, then the pot is 25: raise to 10 + 25.
    assert raise_range(hand) == (20, 35)
    assert ActionType.ALL_IN not in legal(hand)


def test_pot_limit_counts_the_call_in_the_pot() -> None:
    _, hand = deal(PL)
    act(hand, ("raise", 35))

    # Bob has 5 in: he calls 30, the pot is then 80, so he raises to 115.
    assert raise_range(hand) == (60, 115)


def test_pot_limit_after_the_flop_is_the_pot() -> None:
    _, hand = deal(PL)
    to_flop(hand)

    assert raise_range(hand) == (10, 30)
    act(hand, ("raise", 30))
    # Charlie calls 30 into 60: the pot is 90, he raises to 30 + 90.
    assert raise_range(hand) == (60, 120)


def test_pot_limit_refuses_a_raise_above_the_pot() -> None:
    _, hand = deal(PL)

    with pytest.raises(IllegalActionError, match="20-35"):
        act(hand, ("raise", 36))

    with pytest.raises(IllegalActionError):
        act(hand, ("all_in", None))


def test_pot_limit_lets_a_short_stack_go_all_in_below_the_pot() -> None:
    _, hand = deal(PL, stacks=(30, 1000, 1000))

    assert raise_range(hand) == (20, 30)
    assert legal(hand)[ActionType.ALL_IN].amount == 30


# --- Fixed Limit ----------------------------------------------------------------


def test_fixed_limit_raises_one_small_bet_at_a_time_up_to_the_cap() -> None:
    _, hand = deal(FL)

    assert raise_range(hand) == (20, 20)
    assert ActionType.ALL_IN not in legal(hand)

    act(hand, ("raise", 20))
    assert raise_range(hand) == (30, 30)
    act(hand, ("raise", 30))
    assert raise_range(hand) == (40, 40)
    act(hand, ("raise", 40))  # Charlie caps it: the fourth bet.

    assert hand.bets_this_street == 4
    assert set(legal(hand)) == {ActionType.FOLD, ActionType.CALL}

    with pytest.raises(IllegalActionError):
        act(hand, ("raise", 50))


def test_fixed_limit_bets_are_doubled_on_the_turn_and_river() -> None:
    _, hand = deal(FL)
    to_flop(hand)
    assert raise_range(hand) == (10, 10)

    act(hand, ("check", None), ("check", None), ("check", None))
    advance_hand(hand)
    assert raise_range(hand) == (20, 20)

    act(hand, ("raise", 20))
    assert raise_range(hand) == (40, 40)


def test_fixed_limit_refuses_any_other_size() -> None:
    _, hand = deal(FL)

    with pytest.raises(IllegalActionError):
        act(hand, ("raise", 30))


def test_fixed_limit_offers_all_in_only_below_a_full_raise() -> None:
    _, hand = deal(FL, stacks=(16, 1000, 1000))

    assert set(legal(hand)) == {
        ActionType.FOLD,
        ActionType.CALL,
        ActionType.ALL_IN,
    }
    assert legal(hand)[ActionType.ALL_IN].amount == 16


def test_fixed_limit_all_in_of_half_a_bet_is_a_full_raise() -> None:
    _, hand = deal(FL, stacks=(1000, 1000, 25))
    to_flop(hand)
    bob, charlie, alice = (
        hand.table.players[1],
        hand.table.players[2],
        hand.table.players[0],
    )

    act(hand, ("raise", 10))  # Bob bets 10.
    act(hand, ("all_in", None))  # Charlie: all-in to 15, half a bet more.

    assert (hand.current_bet, hand.full_bet, hand.bets_this_street) == (15, 15, 2)
    assert hand.last_raiser is charlie
    assert hand.current_player is alice
    assert raise_range(hand) == (25, 25)  # A full raise above the all-in.

    act(hand, ("call", None))
    assert hand.current_player is bob
    assert raise_range(hand) == (25, 25)  # The betting is reopened for Bob.


def test_fixed_limit_all_in_of_less_than_half_a_bet_is_completed() -> None:
    _, hand = deal(FL, stacks=(1000, 1000, 24))
    to_flop(hand)
    bob, alice = hand.table.players[1], hand.table.players[0]

    act(hand, ("raise", 10))  # Bob bets 10.
    act(hand, ("all_in", None))  # Charlie: all-in to 14, not a raise.

    assert (hand.current_bet, hand.full_bet, hand.bets_this_street) == (14, 10, 1)
    assert hand.current_player is alice
    assert raise_range(hand) == (20, 20)  # Alice completes the raise.

    act(hand, ("call", None))
    assert hand.current_player is bob
    assert set(legal(hand)) == {ActionType.FOLD, ActionType.CALL}  # Not reopened.


def test_fixed_limit_short_all_in_opening_bet_is_completed() -> None:
    _, hand = deal(FL, stacks=(1000, 14, 1000))  # 4 left after the flop.
    to_flop(hand)

    act(hand, ("all_in", None))  # Bob: 4, less than half a bet.

    assert (hand.current_bet, hand.full_bet, hand.bets_this_street) == (4, 0, 0)
    assert raise_range(hand) == (10, 10)


def test_a_straddle_is_the_first_raise_in_fixed_limit() -> None:
    session = create_session(
        ["Alice", "Bob", "Charlie", "Dana"],
        GameConfig(
            small_blind=5, big_blind=10, betting=BettingRules(FL), straddle=True
        ),
    )
    session.table.dealer_index = 0
    hand = start_hand(session, deck=Deck(random.Random(7)))
    dana = session.players[3]

    assert hand.current_bet == 20
    assert hand.bets_this_street == 2
    assert hand.first_to_act is session.players[0]
    assert raise_range(hand) == (30, 30)
    assert dana.current_bet == 20


# --- The betting cap in No Limit ------------------------------------------------


def test_no_limit_with_a_cap_stops_the_raises() -> None:
    _, hand = deal(NL, bet_cap=3)

    act(hand, ("raise", 30), ("raise", 90))  # The big blind, then two raises.

    assert hand.bets_this_street == 3
    assert set(legal(hand)) == {ActionType.FOLD, ActionType.CALL}


def test_a_short_all_in_does_not_count_toward_the_cap() -> None:
    _, hand = deal(NL, stacks=(1000, 1000, 35), bet_cap=3)

    act(hand, ("raise", 30))  # Alice: the second bet.
    act(hand, ("fold", None))  # Bob.
    act(hand, ("all_in", None))  # Charlie: 35, not a full raise.

    assert hand.bets_this_street == 2
    assert set(legal(hand)) == {ActionType.FOLD, ActionType.CALL}  # Not reopened.


def test_no_limit_without_a_cap_raises_until_the_stacks_are_in() -> None:
    _, hand = deal(NL)

    for raise_to in (30, 90, 270, 810):
        act(hand, ("raise", raise_to))

    assert hand.bets_this_street == 5
    assert ActionType.ALL_IN in legal(hand)


# --- Whole hands ------------------------------------------------------------------


@pytest.mark.parametrize("betting", [PL, FL])
def test_the_chips_add_up_after_a_hand_played_to_the_end(
    betting: BettingStructure,
) -> None:
    session, hand = deal(betting, stacks=(1000, 60, 1000))
    act(hand, ("raise", hand.current_bet + 10))

    while not hand.finished:
        if hand.current_player is None:
            advance_hand(hand)
            continue

        actions = legal(hand)
        choice = (
            actions.get(ActionType.ALL_IN)
            or actions.get(ActionType.CALL)
            or actions[ActionType.CHECK]
        )
        assert choice is not None
        apply_action(hand, to_action((choice.type, None)))

    assert sum(player.stack for player in session.players) == 2060
