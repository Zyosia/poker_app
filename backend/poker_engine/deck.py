"""Standard 52-card deck."""

import random
from collections.abc import Sequence

from .constants import RANKS, SUITS, Card


class Deck:
    """Shuffled 52-card deck.

    A seeded ``random.Random`` can be injected to make the order reproducible.
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        self.cards: list[Card] = [rank + suit for rank in RANKS for suit in SUITS]
        (rng or random).shuffle(self.cards)

    @classmethod
    def stacked(cls, first_cards: Sequence[Card]) -> "Deck":
        """A deck dealing ``first_cards`` in this order, then the other cards.

        Used to deal a recorded hand again (hand replayer).
        """
        deck = cls(random.Random(0))
        chosen = set(first_cards)

        if len(chosen) != len(first_cards) or not chosen <= set(deck.cards):
            raise ValueError("A stacked deck needs distinct, valid cards.")

        rest = [card for card in deck.cards if card not in chosen]
        deck.cards = [*first_cards, *rest][::-1]  # ``draw`` takes the last card.

        return deck

    def draw(self) -> Card:
        """Draw and remove the top card."""
        if not self.cards:
            raise RuntimeError("Cannot draw from an empty deck.")
        return self.cards.pop()

    def burn(self) -> Card:
        """Discard the top card."""
        return self.draw()

    @property
    def remaining_cards(self) -> int:
        return len(self.cards)
