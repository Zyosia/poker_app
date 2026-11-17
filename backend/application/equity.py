"""Win probabilities (equity) of hands whose cards are face up.

Used to show each player's chances while the board is dealt after an all-in.
With two cards or fewer to come, every possible board is counted, so the
result is exact. Before the flop (five cards to come, about 1.7 million
boards) it is estimated from a capped number of random boards, drawn with an
RNG of its own, so the game's cards are never affected.

Only the cards face up on the table are known: the folded players' cards are
treated as unknown, as for anyone watching the table.
"""

import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import combinations

from backend.poker_engine.constants import RANKS, SUITS, Card
from backend.poker_engine.hand_evaluator import evaluate_rank

FULL_DECK: tuple[Card, ...] = tuple(rank + suit for rank in RANKS for suit in SUITS)
BOARD_SIZE = 5
MAX_EXACT_CARDS_TO_COME = 2
ESTIMATE_EVALUATIONS = 4000
"""Hand evaluations allowed for an estimate (about 40 ms, so the UI never
stalls): the number of random boards is this divided by the players."""


@dataclass(frozen=True)
class Equity:
    """Each player's share of the pot on average, from 0 to 1."""

    shares: tuple[float, ...]
    """In the order of the hands given; ties count as a share of the pot."""
    exact: bool
    """True when every board was counted, False for an estimate."""


def calculate_equity(
    hands: list[tuple[Card, ...]], board: list[Card], seed: int = 0
) -> Equity:
    """Return the equity of each hand on ``board`` (0 to 5 cards).

    The estimate (three or more cards to come) uses an RNG seeded with
    ``seed``, so the same situation always shows the same numbers.
    """
    if len(hands) < 2:
        raise ValueError("Equity needs at least two hands.")

    if len(board) > BOARD_SIZE:
        raise ValueError("A board has at most five cards.")

    known = {card for hand in hands for card in hand} | set(board)

    if len(known) != sum(len(hand) for hand in hands) + len(board):
        raise ValueError("A card appears twice.")

    remaining = [card for card in FULL_DECK if card not in known]
    to_come = BOARD_SIZE - len(board)

    if to_come <= MAX_EXACT_CARDS_TO_COME:
        runouts = combinations(remaining, to_come)
        return Equity(shares=_shares(hands, board, runouts), exact=True)

    rng = random.Random(seed)
    samples = max(1, ESTIMATE_EVALUATIONS // len(hands))
    runouts = (rng.sample(remaining, to_come) for _ in range(samples))

    return Equity(shares=_shares(hands, board, runouts), exact=False)


def _shares(
    hands: list[tuple[Card, ...]],
    board: list[Card],
    runouts: Iterable[Sequence[Card]],
) -> tuple[float, ...]:
    wins = [0.0] * len(hands)
    boards = 0

    for runout in runouts:
        full_board = [*board, *runout]
        strengths = [evaluate_rank([*hand, *full_board]) for hand in hands]
        best = max(strengths)
        winners = [index for index, value in enumerate(strengths) if value == best]

        for index in winners:
            wins[index] += 1 / len(winners)

        boards += 1

    return tuple(win / boards for win in wins)
