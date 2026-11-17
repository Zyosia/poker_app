"""Each hand's own record of the players dealt in, and the stacked deck."""

import pytest

from backend.poker_engine.actions import Action
from backend.poker_engine.betting import apply_action
from backend.poker_engine.blinds import AnteType, BlindLevel
from backend.poker_engine.constants import ActionType, Position
from backend.poker_engine.deck import Deck
from backend.poker_engine.hand import play_hand, start_hand
from backend.poker_engine.models import Player, SeatRecord
from backend.poker_engine.session import GameConfig, GameSession, create_session


def fold_everything(hand, player) -> Action:
    return Action(type=ActionType.FOLD)


def test_start_hand_records_the_seats_before_the_forced_bets() -> None:
    session = create_session(
        ["Alice", "Bob", "Charlie"], GameConfig(starting_stack=1000)
    )
    session.table.dealer_index = 0
    session.set_blind_level(BlindLevel(10, 20, ante=5, ante_type=AnteType.CLASSIC))
    session.players[2].stack = 700

    hand = start_hand(session)

    assert hand.seats == [
        SeatRecord("Alice", 1000, Position.BTN, tuple(session.players[0].hand)),
        SeatRecord("Bob", 1000, Position.SB, tuple(session.players[1].hand)),
        SeatRecord("Charlie", 700, Position.BB, tuple(session.players[2].hand)),
    ]
    assert all(len(seat.hole_cards) == 2 for seat in hand.seats)
    assert session.players[2].stack == 700 - 5 - 20, "the record kept the stack"


def test_players_not_dealt_in_have_no_seat_record() -> None:
    session = create_session(["Alice", "Bob", "Charlie"], GameConfig())
    session.table.dealer_index = 0
    session.players[1].stack = 0

    hand = start_hand(session)

    assert [seat.name for seat in hand.seats] == ["Alice", "Charlie"]


def test_the_records_of_a_hand_survive_the_next_hands() -> None:
    session = create_session(["Alice", "Bob"], GameConfig())
    session.table.dealer_index = 0
    first = play_hand(session, fold_everything)
    recorded = list(first.seats)
    cards = [tuple(player.hand) for player in session.players]
    stacks = [player.stack for player in session.players]

    session.table.move_dealer()
    play_hand(session, fold_everything)

    assert first.seats == recorded
    assert [seat.hole_cards for seat in first.seats] == cards
    assert [seat.stack for seat in first.seats] == [1000, 1000]
    assert stacks != [1000, 1000], "the players' stacks moved on"


def test_a_stacked_deck_deals_its_cards_first_in_order() -> None:
    deck = Deck.stacked(["AS", "KD", "2C"])

    assert [deck.draw() for _ in range(3)] == ["AS", "KD", "2C"]
    assert deck.remaining_cards == 49
    assert len({deck.draw() for _ in range(49)}) == 49


@pytest.mark.parametrize("cards", [["AS", "AS"], ["ZZ"], ["as"]])
def test_a_stacked_deck_rejects_bad_cards(cards: list[str]) -> None:
    with pytest.raises(ValueError, match="distinct, valid"):
        Deck.stacked(cards)


@pytest.mark.parametrize(
    ("count", "positions"),
    [
        (7, ["BTN", "SB", "BB", "UTG", "LJ", "HJ", "CO"]),
        (8, ["BTN", "SB", "BB", "UTG", "UTG+1", "LJ", "HJ", "CO"]),
        (9, ["BTN", "SB", "BB", "UTG", "UTG+1", "UTG+2", "LJ", "HJ", "CO"]),
    ],
)
def test_full_ring_hands_have_a_position_for_every_player(
    count: int, positions: list[str]
) -> None:
    """Seven to nine players: hands read from other sites' histories."""
    players = [Player(name=f"P{index}", stack=1000) for index in range(count)]
    session = GameSession(players=players, config=GameConfig())
    session.table.dealer_index = 0

    hand = start_hand(session)

    assert [seat.position for seat in hand.seats] == positions
    assert hand.current_player is players[3], "UTG, left of the big blind"

    while not hand.finished:
        apply_action(hand, Action(type=ActionType.FOLD))

    assert hand.payouts == {"P2": 15}, "the big blind wins the blinds"
