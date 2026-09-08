# game/deck.py

from __future__ import annotations

import random

from ..constants import (
    RANKS,
    SUITS,
    Card,
)


class Deck:
    """Standard 52-card Texas Hold'em deck."""

    def __init__(self) -> None:
        self.cards: list[Card] = [rank + suit for rank in RANKS for suit in SUITS]

        self.shuffle()

    def shuffle(self) -> None:
        """Shuffle the remaining cards."""

        random.shuffle(self.cards)

    def draw(self) -> Card:
        """Draw and remove the top card."""

        if not self.cards:
            raise RuntimeError("Cannot draw from an empty deck.")

        return self.cards.pop()

    def burn(self) -> Card:
        """Burn one card."""

        return self.draw()

    @property
    def remaining_cards(self) -> int:
        return len(self.cards)
