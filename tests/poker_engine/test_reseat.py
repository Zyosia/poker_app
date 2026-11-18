"""Seating a new list of players at a table between hands (tournament tables
that break or balance, V3.1)."""

import pytest

from backend.poker_engine.hand import start_hand
from backend.poker_engine.models import Player
from tests.helpers import make_player, make_session


def test_a_table_is_reseated_between_hands_and_old_hands_keep_their_table() -> None:
    alice, bob, carol = (
        make_player(name, stack=1000) for name in ("Alice", "Bob", "Carol")
    )
    session = make_session(alice, bob, carol)
    session.table.dealer_index = 0
    hand = start_hand(session)
    hand.finished = True  # As if everyone had folded to the big blind.
    dave = make_player("Dave", stack=1000)

    session.reseat([alice, carol, dave], dealer_index=1)

    assert [p.name for p in session.players] == ["Alice", "Carol", "Dave"]
    assert session.table.players is session.players
    assert session.table.dealer is carol
    assert [p.name for p in hand.table.players] == ["Alice", "Bob", "Carol"]


def test_a_table_cannot_be_reseated_during_a_hand() -> None:
    alice, bob = (make_player(name, stack=1000) for name in ("Alice", "Bob"))
    session = make_session(alice, bob)
    session.table.dealer_index = 0
    start_hand(session)

    with pytest.raises(RuntimeError):
        session.reseat([alice, bob], dealer_index=1)


def test_a_reseated_table_needs_distinct_players_and_a_dealer_among_them() -> None:
    alice = make_player("Alice", stack=1000)
    session = make_session(alice, make_player("Bob", stack=1000))
    session.table.dealer_index = 0
    too_many = [Player(name=f"P{index}", stack=10) for index in range(10)]

    for players, dealer_index in (
        ([], 0),
        ([alice, alice], 0),
        ([alice], 1),
        (too_many, 0),
    ):
        with pytest.raises(ValueError):
            session.reseat(players, dealer_index)
