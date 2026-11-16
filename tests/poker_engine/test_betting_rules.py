"""No Limit Hold'em betting rules: reopening, minimum bets and legality."""

import pytest

from backend.poker_engine.betting import (
    IllegalActionError,
    apply_action,
    begin_betting_round,
    get_legal_actions,
)
from backend.poker_engine.constants import ActionType, Street
from tests.helpers import (
    allowed_action_types,
    make_hand,
    make_player,
    make_session,
    play_betting_round,
    to_action,
)

# ============================================================
# Short all-in and reopening of the betting
# ============================================================


def test_short_all_in_does_not_reopen_betting_for_player_who_already_acted() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=500)
    charlie = make_player("Charlie", stack=140)

    session = make_session(alice, bob, charlie)
    session.table.dealer_index = 2

    hand = make_hand(session)
    hand.street = Street.FLOP
    hand.min_bet = 10

    begin_betting_round(hand)

    # Alice bets 100, Bob calls, Charlie goes all-in for 140 (a raise of 40,
    # less than the minimum raise of 100).
    apply_action(hand, to_action(("raise", 100)))
    apply_action(hand, to_action(("call", None)))
    apply_action(hand, to_action(("all_in", None)))

    assert hand.current_bet == 140
    assert hand.last_raise_size == 100
    assert hand.last_raiser is alice

    # Alice already acted and only faces 40 more: she may call or fold only.
    assert hand.current_player is alice
    assert allowed_action_types(alice, hand) == ["fold", "call"]

    with pytest.raises(IllegalActionError):
        apply_action(hand, to_action(("raise", 300)))

    with pytest.raises(IllegalActionError):
        apply_action(hand, to_action(("all_in", None)))

    apply_action(hand, to_action(("call", None)))

    assert hand.current_player is bob
    assert allowed_action_types(bob, hand) == ["fold", "call"]

    apply_action(hand, to_action(("call", None)))

    assert hand.current_player is None
    assert alice.current_bet == bob.current_bet == charlie.current_bet == 140


def test_player_who_has_not_acted_may_raise_after_short_all_in() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=140)
    charlie = make_player("Charlie", stack=500)

    session = make_session(alice, bob, charlie)
    session.table.dealer_index = 2

    hand = make_hand(session)
    hand.street = Street.FLOP
    hand.min_bet = 10

    begin_betting_round(hand)

    apply_action(hand, to_action(("raise", 100)))
    apply_action(hand, to_action(("all_in", None)))

    # Charlie has not acted yet. The minimum raise is still a raise of 100
    # over the 140 to call.
    assert hand.current_player is charlie

    raise_action = next(
        action
        for action in get_legal_actions(charlie, hand)
        if action.type == ActionType.RAISE
    )

    assert raise_action.min_amount == 240
    assert raise_action.max_amount == 500


def test_cumulative_short_all_ins_reopen_betting() -> None:
    alice = make_player("Alice", stack=1000)
    bob = make_player("Bob", stack=160)
    charlie = make_player("Charlie", stack=220)

    session = make_session(alice, bob, charlie)
    session.table.dealer_index = 2

    hand = make_hand(session)
    hand.street = Street.FLOP
    hand.min_bet = 10

    called_players, _ = play_betting_round(
        hand,
        [
            # Alice bets 100.
            ("raise", 100),
            # Bob is all-in for 160: a short raise of 60.
            ("all_in", None),
            # Charlie is all-in for 220: another short raise of 60.
            ("all_in", None),
            # Alice now faces 120 more, at least a full raise: she may re-raise,
            # but nobody is left to respond, so she can only call or fold.
            ("call", None),
        ],
    )

    assert called_players == [alice, bob, charlie, alice]
    assert hand.current_bet == 220
    assert alice.current_bet == 220


def test_cumulative_short_all_ins_allow_reraise_when_opponent_can_respond() -> None:
    alice = make_player("Alice", stack=1000)
    bob = make_player("Bob", stack=160)
    charlie = make_player("Charlie", stack=220)
    dave = make_player("Dave", stack=1000)

    session = make_session(alice, bob, charlie, dave)
    session.table.dealer_index = 3

    hand = make_hand(session)
    hand.street = Street.FLOP
    hand.min_bet = 10

    begin_betting_round(hand)

    apply_action(hand, to_action(("raise", 100)))
    apply_action(hand, to_action(("all_in", None)))
    apply_action(hand, to_action(("all_in", None)))
    apply_action(hand, to_action(("call", None)))

    # Alice bet 100 and now faces 220: 120 more is a full raise, so the
    # betting is reopened for her.
    assert hand.current_player is alice
    assert allowed_action_types(alice, hand) == ["fold", "call", "raise", "all_in"]


def test_raise_is_not_offered_when_every_opponent_is_all_in() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=0)
    bob.all_in = True

    session = make_session(alice, bob)
    session.table.dealer_index = 0

    hand = make_hand(session, current_bet=100)
    hand.street = Street.FLOP
    hand.last_raise_size = 100
    bob.current_bet = 100

    assert allowed_action_types(alice, hand) == ["fold", "call"]


# ============================================================
# Minimum bet
# ============================================================


def test_minimum_opening_bet_is_the_big_blind() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=500)

    session = make_session(alice, bob)
    session.table.dealer_index = 0

    hand = make_hand(session)
    hand.street = Street.FLOP
    hand.min_bet = 10

    begin_betting_round(hand)

    assert hand.current_player is bob

    raise_action = next(
        action
        for action in get_legal_actions(bob, hand)
        if action.type == ActionType.RAISE
    )

    assert raise_action.min_amount == 10

    with pytest.raises(IllegalActionError):
        apply_action(hand, to_action(("raise", 5)))


def test_all_in_for_less_than_big_blind_is_a_short_bet() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=4)
    charlie = make_player("Charlie", stack=500)

    session = make_session(alice, bob, charlie)
    session.table.dealer_index = 0

    hand = make_hand(session)
    hand.street = Street.FLOP
    hand.min_bet = 10

    begin_betting_round(hand)

    assert hand.current_player is bob
    assert allowed_action_types(bob, hand) == ["fold", "check", "all_in"]

    apply_action(hand, to_action(("all_in", None)))

    assert hand.current_bet == 4
    assert hand.last_raiser is None

    raise_action = next(
        action
        for action in get_legal_actions(charlie, hand)
        if action.type == ActionType.RAISE
    )

    assert raise_action.min_amount == 14


# ============================================================
# Illegal actions
# ============================================================


def test_check_is_rejected_when_facing_a_bet() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=500)

    session = make_session(alice, bob)
    session.table.dealer_index = 0

    hand = make_hand(session)
    hand.street = Street.FLOP
    hand.min_bet = 10

    begin_betting_round(hand)
    apply_action(hand, to_action(("raise", 50)))

    assert hand.current_player is alice

    with pytest.raises(IllegalActionError):
        apply_action(hand, to_action(("check", None)))

    # A rejected action leaves the state untouched.
    assert hand.current_player is alice
    assert alice.stack == 500
    assert hand.pot == 50


def test_raise_above_stack_is_rejected() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=200)

    session = make_session(alice, bob)
    session.table.dealer_index = 0

    hand = make_hand(session)
    hand.street = Street.FLOP
    hand.min_bet = 10

    begin_betting_round(hand)

    with pytest.raises(IllegalActionError):
        apply_action(hand, to_action(("raise", 201)))

    with pytest.raises(IllegalActionError):
        apply_action(hand, to_action(("raise", None)))


def test_no_action_is_accepted_once_the_round_is_over() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=500)

    session = make_session(alice, bob)
    session.table.dealer_index = 0

    hand = make_hand(session)
    hand.street = Street.FLOP

    play_betting_round(hand, [("check", None), ("check", None)])

    with pytest.raises(IllegalActionError):
        apply_action(hand, to_action(("check", None)))


# ============================================================
# History
# ============================================================


def test_all_in_is_recorded_in_history() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=80)

    session = make_session(alice, bob)
    session.table.dealer_index = 0

    hand = make_hand(session)
    hand.street = Street.FLOP
    hand.min_bet = 10

    begin_betting_round(hand)
    event = apply_action(hand, to_action(("all_in", None)))

    assert hand.actions == [event]
    assert event.player == "Bob"
    assert event.action == "all_in"
    assert event.amount == 80
    assert event.bet_after == 80
    assert event.pot_after == 80
    assert event.bet_initiator is True
