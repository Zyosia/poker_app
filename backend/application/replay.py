"""A recorded hand dealt again through the engine, one step at a time.

The players sit down with the stacks they had, the deck is stacked with the
recorded cards, and every recorded decision is played again through
``apply_action``. The table therefore shows real engine states, and the
engine checks the record: a replay that does not end exactly as recorded is
refused.

A step is what ``PokerGame.step`` does: one decision, or one street dealt
(or the showdown). Step 0 is the hand just dealt, blinds posted.
"""

from collections.abc import Mapping, Sequence

from backend.poker_engine.actions import Action
from backend.poker_engine.betting import IllegalActionError, apply_action
from backend.poker_engine.constants import ActionType, Card
from backend.poker_engine.deck import Deck
from backend.poker_engine.hand import advance_hand, start_hand
from backend.poker_engine.models import ActionEvent, Hand, Player
from backend.poker_engine.session import GameConfig, GameSession

from .equity import FULL_DECK
from .hand_records import HandRecord

BURN_CARDS = 3


class ReplayError(ValueError):
    """A hand cannot be replayed: not fully recorded, or not as the rules play."""


class HandReplay:
    """Deals a recorded hand again and plays it step by step."""

    def __init__(self, record: HandRecord) -> None:
        if record.seats is None:
            raise ReplayError(
                "This hand was saved before V1.1: its hole cards and stacks "
                "were not recorded, so it cannot be replayed."
            )

        if not record.finished:
            raise ReplayError("This hand was not finished: it cannot be replayed.")

        self.record = record
        hand = self.start()
        steps = 0

        while not hand.finished:
            self.advance(hand)
            steps += 1

        if dict(hand.payouts) != dict(record.payouts) or (
            tuple(hand.community_cards) != record.board
        ):
            raise ReplayError("The replayed hand does not end as recorded.")

        self.step_count = steps
        """The steps after the deal; ``hand_at(step_count)`` is the end."""

    def start(self) -> Hand:
        """The hand as dealt: blinds posted, hole cards in hand."""
        record = self.record
        seats = record.seats
        assert seats is not None
        names = [seat.name for seat in seats]

        if record.dealer not in names:
            raise ReplayError("The dealer of the record was not dealt in.")

        session = GameSession(
            players=[Player(name=seat.name, stack=seat.stack) for seat in seats],
            config=GameConfig(),
        )
        session.set_blind_level(record.blind_level)
        session.table.dealer_index = names.index(record.dealer)

        try:
            cards = {seat.name: seat.hole_cards for seat in seats}
            order = deal_order(names, record.dealer, cards, record.board)
            hand = start_hand(session, deck=Deck.stacked(order))
        except (ValueError, RuntimeError) as error:
            raise ReplayError(f"The hand cannot be dealt again: {error}") from error

        if hand.seats != list(seats) or not all(
            _same(played, recorded)
            for played, recorded in zip(hand.actions, record.actions, strict=False)
        ):
            raise ReplayError("The deal does not match the record.")

        return hand

    def advance(self, hand: Hand) -> ActionEvent | None:
        """Play the next step: the recorded decision, or the next street."""
        if hand.finished:
            raise ReplayError("The hand is over.")

        if hand.current_player is None:
            advance_hand(hand)
            return None

        index = len(hand.actions)

        if index >= len(self.record.actions):
            raise ReplayError("The record ends before the hand does.")

        recorded = self.record.actions[index]
        action_type = ActionType(recorded.action)
        amount = recorded.bet_after if action_type == ActionType.RAISE else None

        try:
            event = apply_action(hand, Action(type=action_type, amount=amount))
        except IllegalActionError as error:
            raise ReplayError(f"Action {index + 1} is not legal: {error}") from error

        if not _same(event, recorded):
            raise ReplayError(f"Action {index + 1} does not match the record.")

        return event

    def hand_at(self, step: int) -> Hand:
        """The hand after ``step`` steps (0 to ``step_count``)."""
        if not 0 <= step <= self.step_count:
            raise ValueError(f"Step {step} is outside 0-{self.step_count}.")

        hand = self.start()

        for _ in range(step):
            self.advance(hand)

        return hand


def deal_order(
    names: Sequence[str],
    dealer: str,
    hole_cards: Mapping[str, Sequence[Card]],
    board: Sequence[Card],
) -> list[Card]:
    """The cards of a hand in the order the engine deals them.

    Hole cards one at a time from the left of the dealer (``names`` are the
    players dealt in, clockwise), then the board with a burn card before each
    street; the burn cards are cards nobody holds.
    """
    position = list(names).index(dealer)
    order = [*names[position + 1 :], *names[: position + 1]]
    cards = [hole_cards[name][0] for name in order]
    cards += [hole_cards[name][1] for name in order]
    known = {*cards, *board}
    burns = [card for card in FULL_DECK if card not in known][:BURN_CARDS]

    for burn, street_cards in zip(
        burns, (board[:3], board[3:4], board[4:5]), strict=True
    ):
        if street_cards:
            cards += [burn, *street_cards]

    return cards


def _same(played: ActionEvent, recorded: ActionEvent) -> bool:
    return (played.player, played.action, played.amount) == (
        recorded.player,
        recorded.action,
        recorded.amount,
    )
