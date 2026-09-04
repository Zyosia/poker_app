import pytest

from backend.game.showdown import (
    distribute_pots,
    evaluate_showdown,
    get_best_players,
    resolve_hand,
)
from tests.game.conftest import make_hand, make_player, make_session


def test_resolve_by_fold_awards_entire_pot_to_last_active_player() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)

    session = make_session(alice, bob)
    session.table.dealer_index = 0

    hand = make_hand(session)
    hand.pot = 200

    bob.folded = True

    resolve_hand(hand)

    assert alice.stack == 200
    assert bob.stack == 0

    assert hand.pot == 0
    assert hand.finished is True
    assert hand.current_player is None
    assert hand.winner_by_fold is alice
    assert hand.payouts == {"Alice": 200}


def test_resolve_hand_requires_five_community_cards_for_showdown() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)

    session = make_session(alice, bob)
    session.table.dealer_index = 0

    hand = make_hand(session)
    hand.pot = 200

    alice.hand = ["As", "Ah"]
    bob.hand = ["Ks", "Kh"]

    hand.community_cards = [
        "2c",
        "7d",
        "9h",
        "Jc",
    ]

    with pytest.raises(
        RuntimeError,
        match="Showdown requires a complete five-card board.",
    ):
        resolve_hand(hand)


def test_showdown_evaluates_only_active_players() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)

    session = make_session(alice, bob, charlie)
    session.table.dealer_index = 0

    hand = make_hand(session)

    hand.community_cards = [
        "2c",
        "7d",
        "9h",
        "Jc",
        "Qs",
    ]

    alice.hand = ["As", "Kd"]
    bob.hand = ["Ac", "Kh"]
    charlie.hand = ["Ah", "Ad"]

    charlie.folded = True

    evaluate_showdown(
        hand=hand,
        players=hand.table.get_active_players(),
    )

    assert set(hand.showdown_evaluations) == {"Alice", "Bob"}
    assert "Charlie" not in hand.showdown_evaluations


def test_resolve_hand_awards_pot_to_best_hand() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)

    session = make_session(alice, bob)
    session.table.dealer_index = 0

    hand = make_hand(session)

    alice.hand = ["As", "Ah"]
    bob.hand = ["Ks", "Kh"]

    hand.community_cards = [
        "2c",
        "7d",
        "9h",
        "Jc",
        "Qs",
    ]

    alice.total_contribution = 100
    bob.total_contribution = 100
    hand.pot = 200

    resolve_hand(hand)

    assert alice.stack == 200
    assert bob.stack == 0

    assert hand.pot == 0
    assert hand.finished is True

    assert hand.payouts == {
        "Alice": 200,
    }

    assert len(hand.pot_results) == 1
    assert hand.pot_results[0].amount == 200
    assert hand.pot_results[0].eligible_players == (
        "Alice",
        "Bob",
    )
    assert hand.pot_results[0].winners == ("Alice",)


def test_resolve_hand_splits_tied_pot() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)

    session = make_session(alice, bob)
    session.table.dealer_index = 0

    hand = make_hand(session)

    alice.hand = ["As", "Kd"]
    bob.hand = ["Ac", "Kh"]

    hand.community_cards = [
        "2c",
        "3d",
        "4h",
        "5c",
        "6s",
    ]

    alice.total_contribution = 100
    bob.total_contribution = 100
    hand.pot = 200

    resolve_hand(hand)

    assert alice.stack == 100
    assert bob.stack == 100

    assert hand.pot == 0
    assert hand.payouts == {
        "Alice": 100,
        "Bob": 100,
    }

    assert len(hand.pot_results) == 1
    assert hand.pot_results[0].winners == (
        "Alice",
        "Bob",
    )


def test_distribute_pots_rejects_pot_accounting_mismatch() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)

    session = make_session(alice, bob)
    session.table.dealer_index = 0

    hand = make_hand(session)

    alice.total_contribution = 100
    bob.total_contribution = 100

    hand.pot = 150

    with pytest.raises(
        RuntimeError,
        match="Pot accounting mismatch",
    ):
        distribute_pots(hand)


def test_get_best_players_requires_showdown_evaluations() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)

    session = make_session(alice, bob)
    session.table.dealer_index = 0

    hand = make_hand(session)

    with pytest.raises(
        RuntimeError,
        match="No showdown evaluation for Alice.",
    ):
        get_best_players(
            hand=hand,
            players=[alice, bob],
        )
