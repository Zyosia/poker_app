"""Text shown to the user for cards, actions and results."""

from backend.poker_engine.constants import ActionType, Card
from backend.poker_engine.models import ActionEvent, Hand

SUIT_SYMBOLS = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
RANK_LABELS = {"T": "10"}


def format_card(card: Card) -> str:
    """Return a card as rank and suit symbol, for example "A♠"."""
    rank, suit = card[0], card[1]

    return f"{RANK_LABELS.get(rank, rank)}{SUIT_SYMBOLS[suit]}"


def format_cards(cards: list[Card] | tuple[Card, ...]) -> str:
    return " ".join(format_card(card) for card in cards)


def describe_action(event: ActionEvent) -> str:
    """Return a short description of an action, for example "raises to 40"."""
    if event.action == "post_sb":
        return f"posts small blind {event.amount}"

    if event.action == "post_bb":
        return f"posts big blind {event.amount}"

    if event.action == "post_ante":
        return f"posts ante {event.amount}"

    if event.action == ActionType.FOLD:
        return "folds"

    if event.action == ActionType.CHECK:
        return "checks"

    if event.action == ActionType.CALL:
        return f"calls {event.amount}"

    if event.action == ActionType.ALL_IN:
        return f"is all-in for {event.bet_after}"

    if event.bet_initiator:
        return f"bets {event.bet_after}"

    return f"raises to {event.bet_after}"


def describe_result(hand: Hand) -> list[str]:
    """Return one line per winner of a finished hand."""
    if hand.winner_by_fold is not None:
        amount = hand.payouts.get(hand.winner_by_fold.name, 0)
        return [f"{hand.winner_by_fold.name} wins {amount}"]

    lines = []

    for name, amount in hand.payouts.items():
        evaluation = hand.showdown_evaluations.get(name)
        suffix = f" with {evaluation.name}" if evaluation is not None else ""
        lines.append(f"{name} wins {amount}{suffix}")

    return lines
