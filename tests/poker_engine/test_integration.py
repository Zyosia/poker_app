from __future__ import annotations

import pytest

from backend.poker_engine.hand import play_hand
from backend.poker_engine.session import GameConfig, create_session
from tests.helpers import scripted_actions


def test_complete_hand_reaches_showdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A normal hand reaches the river and is resolved at showdown."""

    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=100,
            small_blind=5,
            big_blind=10,
        ),
    )

    session.table.dealer_index = 0

    initial_total = sum(player.stack for player in session.players)

    choose_action = scripted_actions(
        [
            # PREFLOP: Alice BTN, Bob SB, Charlie BB.
            ("call", None),
            ("call", None),
            ("check", None),
            # FLOP: Bob, Charlie, Alice.
            ("check", None),
            ("check", None),
            ("check", None),
            # TURN.
            ("check", None),
            ("check", None),
            ("check", None),
            # RIVER.
            ("check", None),
            ("check", None),
            ("check", None),
        ],
    )

    hand = play_hand(session, choose_action)

    assert hand.finished is True
    assert hand.street == "RIVER"
    assert len(hand.community_cards) == 5
    assert hand.pot == 0

    assert len(hand.showdown_evaluations) == 3
    assert len(hand.pot_results) == 1

    assert sum(player.stack for player in session.players) == initial_total
    assert sum(hand.payouts.values()) == 30


def test_hand_ends_by_fold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hand ends immediately when all opponents fold."""

    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=100,
            small_blind=5,
            big_blind=10,
        ),
    )

    session.table.dealer_index = 0

    choose_action = scripted_actions(
        [
            # Alice BTN raises to 30.
            ("raise", 30),
            # Bob SB folds.
            ("fold", None),
            # Charlie BB folds.
            ("fold", None),
        ],
    )

    hand = play_hand(session, choose_action)

    alice, bob, charlie = session.players

    assert hand.finished is True
    assert hand.winner_by_fold is alice
    assert hand.showdown_evaluations == {}
    assert hand.pot == 0

    assert alice.stack == 115
    assert bob.stack == 95
    assert charlie.stack == 90

    assert hand.payouts == {
        "Alice": 45,
    }

    assert bob.folded is True
    assert charlie.folded is True


def test_all_in_hand_auto_runs_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When every remaining player is all-in, the board runs out automatically."""

    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=30,
            small_blind=5,
            big_blind=10,
        ),
    )

    session.table.dealer_index = 0

    initial_total = sum(player.stack for player in session.players)

    choose_action = scripted_actions(
        [
            # PREFLOP.
            # Alice BTN, Bob SB, Charlie BB.
            ("all_in", None),
            ("all_in", None),
            ("all_in", None),
        ],
    )

    hand = play_hand(session, choose_action)

    assert hand.finished is True
    assert len(hand.community_cards) == 5
    assert hand.pot == 0

    assert all(player.all_in for player in session.players)

    assert len(hand.showdown_evaluations) == 3

    assert sum(player.stack for player in session.players) == initial_total
    assert sum(hand.payouts.values()) == 90


def test_hand_with_side_pot_reaches_showdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A complete hand with unequal stacks creates and distributes a side pot."""

    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=50,
            small_blind=5,
            big_blind=10,
        ),
    )

    # Give Bob and Charlie a larger stack so the hand can create a side pot.
    bob = session.players[1]
    bob.stack = 100
    charlie = session.players[2]
    charlie.stack = 200

    session.table.dealer_index = 0

    initial_total = sum(player.stack for player in session.players)

    choose_action = scripted_actions(
        [
            # PREFLOP.
            # Alice BTN → all-in for 50.
            ("all_in", None),
            # Bob SB: call Alice's 50.
            ("call", None),
            # Charlie BB: call Alice's 50.
            ("call", None),
            # FLOP: Bob first.
            # Bob goes all-in for another 50.
            ("all_in", None),
            # Charlie matches the side-pot bet.
            ("call", None),
        ],
    )

    hand = play_hand(session, choose_action)

    alice, bob, charlie = session.players

    assert hand.finished is True
    assert len(hand.community_cards) == 5
    assert hand.pot == 0

    assert alice.total_contribution == 50
    assert bob.total_contribution == 100
    assert charlie.total_contribution == 100

    assert len(hand.pot_results) == 2

    pot_amounts = [pot_result.amount for pot_result in hand.pot_results]

    assert sorted(pot_amounts) == [100, 150]

    assert alice.stack >= 0
    assert bob.stack >= 0
    assert charlie.stack >= 100

    assert sum(player.stack for player in session.players) == initial_total
    assert sum(hand.payouts.values()) == 250


def test_multiple_hands_preserve_state_and_chip_integrity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Several consecutive hands can be played without losing chips."""

    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=100,
            small_blind=5,
            big_blind=10,
        ),
    )

    session.table.dealer_index = 0

    initial_total = sum(player.stack for player in session.players)

    choose_action = scripted_actions(
        [
            # --------------------------------------------------
            # HAND #1
            # Dealer: Alice
            # Preflop: Alice, Bob, Charlie.
            # --------------------------------------------------
            ("call", None),
            ("call", None),
            ("check", None),
            # Flop: Bob, Charlie, Alice.
            ("check", None),
            ("check", None),
            ("check", None),
            # Turn.
            ("check", None),
            ("check", None),
            ("check", None),
            # River.
            ("check", None),
            ("check", None),
            ("check", None),
            # --------------------------------------------------
            # HAND #2
            # Dealer: Bob
            # Preflop: Charlie, Alice, Bob.
            # --------------------------------------------------
            ("call", None),
            ("call", None),
            ("check", None),
            # Flop: Charlie, Alice, Bob.
            ("check", None),
            ("check", None),
            ("check", None),
            # Turn.
            ("check", None),
            ("check", None),
            ("check", None),
            # River.
            ("check", None),
            ("check", None),
            ("check", None),
        ],
    )

    hand_one = play_hand(session, choose_action)

    assert hand_one.finished is True
    assert session.hand_number == 1
    assert len(hand_one.community_cards) == 5

    assert sum(player.stack for player in session.players) == initial_total

    session.table.move_dealer()

    assert session.table.dealer is session.players[1]

    hand_two = play_hand(session, choose_action)

    assert hand_two.finished is True
    assert session.hand_number == 2
    assert len(hand_two.community_cards) == 5

    assert sum(player.stack for player in session.players) == initial_total

    session.table.move_dealer()

    assert session.table.dealer is session.players[2]


def test_dealer_rotation_is_applied_between_complete_hands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dealer moves clockwise between complete hands."""

    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=100,
            small_blind=5,
            big_blind=10,
        ),
    )

    session.table.dealer_index = 0

    choose_action = scripted_actions(
        [
            # HAND #1
            ("call", None),
            ("call", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            # HAND #2
            ("call", None),
            ("call", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            # HAND #3
            ("call", None),
            ("call", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
        ],
    )

    assert session.table.dealer is session.players[0]

    hand_one = play_hand(session, choose_action)

    assert hand_one.finished is True
    assert hand_one.table.dealer is session.players[0]

    session.table.move_dealer()

    assert session.table.dealer is session.players[1]

    hand_two = play_hand(session, choose_action)

    assert hand_two.finished is True
    assert hand_two.table.dealer is session.players[1]

    session.table.move_dealer()

    assert session.table.dealer is session.players[2]

    hand_three = play_hand(session, choose_action)

    assert hand_three.finished is True
    assert hand_three.table.dealer is session.players[2]

    session.table.move_dealer()

    assert session.table.dealer is session.players[0]


def test_chip_integrity_is_preserved_across_a_complete_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The total number of chips remains constant throughout several hands."""

    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=100,
            small_blind=5,
            big_blind=10,
        ),
    )

    session.table.dealer_index = 0

    initial_total = sum(player.stack for player in session.players)

    choose_action = scripted_actions(
        [
            # HAND #1
            ("call", None),
            ("call", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            # HAND #2
            ("call", None),
            ("call", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
        ],
    )

    hand_one = play_hand(session, choose_action)

    assert hand_one.finished is True
    assert hand_one.pot == 0
    assert sum(player.stack for player in session.players) == initial_total

    session.table.move_dealer()

    hand_two = play_hand(session, choose_action)

    assert hand_two.finished is True
    assert hand_two.pot == 0
    assert sum(player.stack for player in session.players) == initial_total
