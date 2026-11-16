"""Standard 52-card deck."""

import random

from .constants import RANKS, SUITS, Card


class Deck:
    """Shuffled 52-card deck.

    A seeded ``random.Random`` can be injected to make the order reproducible.
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        self.cards: list[Card] = [rank + suit for rank in RANKS for suit in SUITS]
        (rng or random).shuffle(self.cards)

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
