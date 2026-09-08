from unittest.mock import patch

from backend.game.engine.betting import betting_round
from backend.game.models.actions import (
    all_in,
    call,
    fold,
    put_chips_in_pot,
    raise_bet,
)
from tests.game.conftest import make_hand, make_player, make_session


def get_total_chips(players, hand) -> int:
    """Return all chips currently owned by players or committed to the pot."""
    return sum(player.stack for player in players) + hand.pot


# ============================================================
# Basic chip movement
# ============================================================


def test_put_chips_in_pot_preserves_chip_integrity() -> None:
    alice = make_player("Alice", stack=100)

    session = make_session(alice)
    hand = make_hand(session)

    initial_total = get_total_chips(
        players=[alice],
        hand=hand,
    )

    put_chips_in_pot(
        player=alice,
        hand=hand,
        amount=30,
    )

    assert alice.stack == 70
    assert alice.current_bet == 30
    assert alice.total_contribution == 30
    assert hand.pot == 30

    assert (
        get_total_chips(
            players=[alice],
            hand=hand,
        )
        == initial_total
    )


def test_call_preserves_chip_integrity() -> None:
    alice = make_player("Alice", stack=100)

    session = make_session(alice)
    hand = make_hand(
        session,
        current_bet=40,
    )

    alice.current_bet = 10

    initial_total = get_total_chips(
        players=[alice],
        hand=hand,
    )

    call(
        player=alice,
        hand=hand,
    )

    assert alice.stack == 70
    assert alice.current_bet == 40
    assert alice.total_contribution == 30
    assert hand.pot == 30

    assert (
        get_total_chips(
            players=[alice],
            hand=hand,
        )
        == initial_total
    )


def test_raise_preserves_chip_integrity() -> None:
    alice = make_player("Alice", stack=100)

    session = make_session(alice)
    hand = make_hand(
        session,
        current_bet=20,
    )

    alice.current_bet = 20
    hand.last_raise_size = 20

    initial_total = get_total_chips(
        players=[alice],
        hand=hand,
    )

    raise_bet(
        player=alice,
        hand=hand,
        raise_to=40,
    )

    assert alice.stack == 80
    assert alice.current_bet == 40
    assert alice.total_contribution == 20
    assert hand.pot == 20

    assert (
        get_total_chips(
            players=[alice],
            hand=hand,
        )
        == initial_total
    )


def test_all_in_preserves_chip_integrity() -> None:
    alice = make_player("Alice", stack=75)

    session = make_session(alice)
    hand = make_hand(session)

    initial_total = get_total_chips(
        players=[alice],
        hand=hand,
    )

    all_in(
        player=alice,
        hand=hand,
    )

    assert alice.stack == 0
    assert alice.current_bet == 75
    assert alice.total_contribution == 75
    assert alice.all_in is True
    assert hand.pot == 75

    assert (
        get_total_chips(
            players=[alice],
            hand=hand,
        )
        == initial_total
    )


# ============================================================
# Multi-player betting
# ============================================================


def test_betting_round_preserves_chip_integrity() -> None:
    alice = make_player("Alice", stack=100)
    bob = make_player("Bob", stack=100)
    charlie = make_player("Charlie", stack=100)

    session = make_session(
        alice,
        bob,
        charlie,
    )

    session.table.dealer_index = 0

    hand = make_hand(
        session,
        current_bet=10,
    )
    hand.street = "PREFLOP"
    hand.first_to_act = alice

    alice.current_bet = 0
    bob.current_bet = 0
    charlie.current_bet = 10

    initial_total = get_total_chips(
        players=[alice, bob, charlie],
        hand=hand,
    )

    with patch(
        "backend.game.engine.betting.ask_player_action",
        side_effect=[
            ("call", None),
            ("call", None),
            ("check", None),
        ],
    ):
        result = betting_round(
            session=session,
            hand=hand,
        )

    assert result is True

    assert alice.current_bet == 10
    assert bob.current_bet == 10
    assert charlie.current_bet == 10

    assert hand.pot == 20

    assert (
        get_total_chips(
            players=[alice, bob, charlie],
            hand=hand,
        )
        == initial_total
    )


def test_different_player_contributions_preserve_chip_integrity() -> None:
    alice = make_player("Alice", stack=100)
    bob = make_player("Bob", stack=100)
    charlie = make_player("Charlie", stack=100)

    session = make_session(
        alice,
        bob,
        charlie,
    )

    hand = make_hand(session)

    initial_total = get_total_chips(
        players=[alice, bob, charlie],
        hand=hand,
    )

    put_chips_in_pot(
        player=alice,
        hand=hand,
        amount=20,
    )

    put_chips_in_pot(
        player=bob,
        hand=hand,
        amount=50,
    )

    put_chips_in_pot(
        player=charlie,
        hand=hand,
        amount=80,
    )

    assert alice.stack == 80
    assert bob.stack == 50
    assert charlie.stack == 20

    assert alice.current_bet == 20
    assert bob.current_bet == 50
    assert charlie.current_bet == 80

    assert hand.pot == 150

    assert (
        get_total_chips(
            players=[alice, bob, charlie],
            hand=hand,
        )
        == initial_total
    )


# ============================================================
# Non-chip actions
# ============================================================


def test_fold_does_not_change_chip_integrity() -> None:
    alice = make_player("Alice", stack=100)

    session = make_session(alice)
    hand = make_hand(session)

    put_chips_in_pot(
        player=alice,
        hand=hand,
        amount=40,
    )

    initial_total = get_total_chips(
        players=[alice],
        hand=hand,
    )

    fold(alice)

    assert alice.folded is True
    assert alice.stack == 60
    assert alice.current_bet == 40
    assert alice.total_contribution == 40
    assert hand.pot == 40

    assert (
        get_total_chips(
            players=[alice],
            hand=hand,
        )
        == initial_total
    )
