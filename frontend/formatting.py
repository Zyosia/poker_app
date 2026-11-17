"""Text shown to the user for cards, amounts, actions and results."""

import math

from backend.poker_engine.constants import RANKS, SUITS, ActionType, Card
from backend.poker_engine.models import ActionEvent, Hand

SUIT_SYMBOLS = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
RANK_LABELS = {"T": "10"}


def format_chips(chips: int) -> str:
    """Return a chip amount with spaces between thousands: "12 500"."""
    return f"{chips:,}".replace(",", " ")


def format_big_blinds(chips: int, big_blind: int) -> str:
    """Return a chip amount in big blinds, to one decimal place: "42.5 BB".

    A trailing ".0" is dropped ("20 BB"). Rounding is exact (half up), in
    integer arithmetic, so a big blind that does not divide the amount never
    shows a floating-point artefact.
    """
    if big_blind <= 0:
        raise ValueError("The big blind must be positive.")

    tenths = (abs(chips) * 20 + big_blind) // (2 * big_blind)
    whole, tenth = divmod(tenths, 10)
    sign = "-" if chips < 0 and tenths else ""
    text = format_chips(whole) + (f".{tenth}" if tenth else "")

    return f"{sign}{text} BB"


def format_amount(chips: int, big_blind: int | None = None) -> str:
    """Return an amount in chips, or in big blinds when ``big_blind`` is set."""
    if big_blind is None:
        return format_chips(chips)

    return format_big_blinds(chips, big_blind)


def big_blinds_to_chips(
    big_blinds: float, big_blind: int, minimum: int, maximum: int
) -> int:
    """Convert an amount typed in big blinds to chips, within a legal range.

    The amount is rounded to the nearest chip, then kept between ``minimum``
    and ``maximum`` (the legal "raise to" range).
    """
    if minimum > maximum:
        raise ValueError("The minimum exceeds the maximum.")

    chips = math.floor(big_blinds * big_blind + 0.5)  # Half up, like the display.

    return max(minimum, min(maximum, chips))


def format_card(card: Card) -> str:
    """Return a card as rank and suit symbol, for example "A♠"."""
    rank, suit = card[0], card[1]

    return f"{RANK_LABELS.get(rank, rank)}{SUIT_SYMBOLS[suit]}"


def format_cards(cards: list[Card] | tuple[Card, ...]) -> str:
    return " ".join(format_card(card) for card in cards)


def parse_cards(text: str) -> tuple[Card, ...]:
    """Read cards typed by the user: "AsKd", "As Kd", "A♠ K♦" or "10h 9h".

    Raises ValueError with a message for the user when a card is not valid
    or appears twice.
    """
    normalized = text.upper().replace("10", "T")

    for suit, symbol in SUIT_SYMBOLS.items():
        normalized = normalized.replace(symbol, suit)

    letters = "".join(character for character in normalized if character not in " ,")

    if len(letters) % 2:
        raise ValueError(f"“{text.strip()}”: a card is a rank and a suit, like As.")

    cards = tuple(letters[index : index + 2] for index in range(0, len(letters), 2))

    for card in cards:
        if card[0] not in RANKS or card[1] not in SUITS:
            raise ValueError(
                f"“{card}” is not a card (ranks 2-9 T J Q K A, suits s h d c)."
            )

    if len(set(cards)) != len(cards):
        raise ValueError("A card appears twice.")

    return cards


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
