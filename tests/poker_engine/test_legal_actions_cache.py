"""The legal actions of the current decision are computed once and cached."""

import pytest

from backend.poker_engine.actions import Action
from backend.poker_engine.betting import (
    IllegalActionError,
    apply_action,
    get_current_legal_actions,
    get_legal_actions,
)
from backend.poker_engine.constants import ActionType
from backend.poker_engine.hand import start_hand
from backend.poker_engine.models import Hand
from backend.poker_engine.session import GameConfig, create_session


def started_hand() -> Hand:
    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(starting_stack=1000, small_blind=5, big_blind=10),
    )
    session.table.dealer_index = 0  # Alice on the button, first to act.

    return start_hand(session)


def test_cached_actions_are_the_legal_actions_of_the_current_player() -> None:
    hand = started_hand()
    player = hand.current_player
    assert player is not None and player.name == "Alice"

    assert get_current_legal_actions(hand) == get_legal_actions(player, hand)


def test_actions_are_reused_until_the_state_changes() -> None:
    hand = started_hand()

    first = get_current_legal_actions(hand)

    assert get_current_legal_actions(hand) is first


def test_actions_are_recomputed_for_the_next_player() -> None:
    hand = started_hand()
    get_current_legal_actions(hand)

    apply_action(hand, Action(type=ActionType.RAISE, amount=30))
    bob = hand.current_player
    assert bob is not None and bob.name == "Bob"

    actions = get_current_legal_actions(hand)

    assert actions == get_legal_actions(bob, hand)
    call = next(action for action in actions if action.type == ActionType.CALL)
    assert call.amount == 25


def test_a_stack_change_invalidates_the_cache() -> None:
    hand = started_hand()
    alice = hand.current_player
    assert alice is not None
    get_current_legal_actions(hand)

    alice.stack = 10  # Only enough to call: no raise any more.

    types = [action.type for action in get_current_legal_actions(hand)]

    assert ActionType.RAISE not in types
    assert types == [action.type for action in get_legal_actions(alice, hand)]


def test_no_cached_actions_without_a_player_to_act() -> None:
    hand = started_hand()
    hand.current_player = None

    with pytest.raises(IllegalActionError):
        get_current_legal_actions(hand)
