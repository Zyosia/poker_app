# game/deck.py

import random
from game.constants import RANKS, SUITS


class Deck:
    def __init__(self):
        self.cards = [
            rank + suit
            for rank in RANKS
            for suit in SUITS
        ]

        self.shuffle()

    def shuffle(self):
        random.shuffle(self.cards)

    def draw(self):
        return self.cards.pop()

    def burn(self):
        self.cards.pop()