"""Win probabilities (equity) of poker hands.

Two uses:

- **The run-out** (V1.0.1, ``calculate_equity``): the chances of the hands
  face up while the board is dealt after an all-in. With two cards or fewer
  to come, every possible board is counted, so the result is exact. Before
  the flop (about 1.7 million boards) it is estimated from a capped number
  of random boards, so the table never stalls.
- **The equity calculator** (V1.1, ``EquityCalculator``): any hands, some of
  them unknown ("random"), on any board. Every board is counted when every
  hand is known and there are few enough boards; otherwise random boards
  (Monte Carlo) are drawn, as many as the caller asks for, in steps.

The random boards come from an RNG of their own, so the game's cards are
never affected, and the same seed always gives the same numbers. Only the
cards given are known: anyone else's cards count as unknown.
"""

import math
import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import combinations

from backend.poker_engine.constants import MAX_TABLE_SEATS, RANKS, SUITS, Card
from backend.poker_engine.hand_evaluator import evaluate_rank

FULL_DECK: tuple[Card, ...] = tuple(rank + suit for rank in RANKS for suit in SUITS)
BOARD_SIZE = 5
HOLE_CARDS = 2
MAX_EXACT_CARDS_TO_COME = 2
ESTIMATE_EVALUATIONS = 4000
"""Hand evaluations allowed for a run-out estimate (about 40 ms, so the UI
never stalls): the number of random boards is this divided by the players."""
EXACT_BOARD_LIMIT = 50_000
"""The calculator counts every board up to this many (every hand known)."""
CONFIDENCE_Z = 1.96
"""Normal quantile of a 95% margin of error."""


@dataclass(frozen=True)
class Equity:
    """Each player's share of the pot on average, from 0 to 1."""

    shares: tuple[float, ...]
    """In the order of the hands given; ties count as a share of the pot."""
    exact: bool
    """True when every board was counted, False for an estimate."""


@dataclass(frozen=True)
class EquityResult:
    """What the calculator has found so far, hand by hand."""

    equity: tuple[float, ...]
    """Share of the pot on average (a tie counts as a share)."""
    wins: tuple[float, ...]
    """Share of the boards won alone."""
    ties: tuple[float, ...]
    """Share of the boards split with other hands."""
    boards: int
    exact: bool
    margins: tuple[float, ...] | None
    """95% margin of error of each equity; None when exact."""


class EquityCalculator:
    """Equity of 2 to 6 hands, known or random, on a board of 0 to 5 cards."""

    def __init__(
        self,
        hands: Sequence[Sequence[Card] | None],
        board: Sequence[Card] = (),
        seed: int | None = None,
        exact_limit: float = EXACT_BOARD_LIMIT,
    ) -> None:
        """``None`` (or no cards) is a random hand. ``seed`` drives the random
        boards; up to ``exact_limit`` boards, every board is counted instead.
        """
        if not 2 <= len(hands) <= MAX_TABLE_SEATS:
            raise ValueError(f"Equity needs 2 to {MAX_TABLE_SEATS} hands.")

        if len(board) > BOARD_SIZE:
            raise ValueError("A board has at most five cards.")

        known_hands = [tuple(hand) if hand else None for hand in hands]

        if any(hand is not None and len(hand) != HOLE_CARDS for hand in known_hands):
            raise ValueError("A hand has two cards, or none for a random hand.")

        known = [card for hand in known_hands if hand for card in hand] + list(board)
        known_set = set(known)

        if not known_set <= set(FULL_DECK):
            raise ValueError("Unknown card.")

        if len(known_set) != len(known):
            raise ValueError("A card appears twice.")

        self._hands = known_hands
        self._fixed_hands = [hand for hand in known_hands if hand is not None]
        self._random_cards = HOLE_CARDS * (len(known_hands) - len(self._fixed_hands))
        self._board = list(board)
        self._remaining = [card for card in FULL_DECK if card not in known_set]
        self._to_come = BOARD_SIZE - len(board)
        boards = math.comb(len(self._remaining), self._to_come)
        self.exact = not self._random_cards and boards <= exact_limit
        self.total_boards: int | None = boards if self.exact else None
        """Every possible board, when they are all counted."""
        self._runouts: Iterator[tuple[Card, ...]] = combinations(
            self._remaining, self._to_come
        )
        self._rng = random.Random(seed)

        count = len(hands)
        self._equity = [0.0] * count
        self._squares = [0.0] * count
        self._wins = [0] * count
        self._ties = [0] * count
        self._boards = 0

    @property
    def boards(self) -> int:
        """Boards counted so far."""
        return self._boards

    @property
    def finished(self) -> bool:
        """True once every board of an exact calculation was counted."""
        return self.exact and self._boards == self.total_boards

    def run(self, boards: int) -> int:
        """Count up to ``boards`` more boards; returns how many were counted.

        An exact calculation stops after its last board.
        """
        evaluate = evaluate_rank  # Looked up once per call (tests replace it).
        board = self._board
        equity, squares, wins, ties = (
            self._equity,
            self._squares,
            self._wins,
            self._ties,
        )
        counted = 0

        for _ in range(boards):
            dealt = self._deal()

            if dealt is None:
                break

            hands, full_board = dealt
            strengths = [evaluate([*hand, *board, *full_board]) for hand in hands]
            best = max(strengths)
            winners = [index for index, value in enumerate(strengths) if value == best]
            share = 1 / len(winners)

            for index in winners:
                equity[index] += share
                squares[index] += share * share

                if len(winners) == 1:
                    wins[index] += 1
                else:
                    ties[index] += 1

            counted += 1

        self._boards += counted

        return counted

    def _deal(self) -> tuple[list[tuple[Card, ...]], Sequence[Card]] | None:
        """The hands and the cards to come of the next board; None at the end."""
        if self.exact:
            runout = next(self._runouts, None)

            return None if runout is None else (self._fixed_hands, runout)

        drawn = self._rng.sample(self._remaining, self._random_cards + self._to_come)

        if not self._random_cards:
            return self._fixed_hands, drawn

        hands: list[tuple[Card, ...]] = []
        dealt = 0

        for hand in self._hands:
            if hand is None:
                hand = (drawn[dealt], drawn[dealt + 1])
                dealt += HOLE_CARDS

            hands.append(hand)

        return hands, drawn[dealt:]

    def result(self) -> EquityResult:
        boards = self._boards

        if boards == 0:
            raise RuntimeError("No board has been counted yet.")

        equity = tuple(total / boards for total in self._equity)
        margins = None

        if not self.exact:
            margins = tuple(
                CONFIDENCE_Z * math.sqrt(max(0.0, square / boards - mean**2) / boards)
                for square, mean in zip(self._squares, equity, strict=True)
            )

        return EquityResult(
            equity=equity,
            wins=tuple(count / boards for count in self._wins),
            ties=tuple(count / boards for count in self._ties),
            boards=boards,
            exact=self.exact,
            margins=margins,
        )


def calculate_equity(
    hands: list[tuple[Card, ...]], board: list[Card], seed: int = 0
) -> Equity:
    """Return the equity of each hand face up on ``board`` (0 to 5 cards).

    Exact with two cards or fewer to come; otherwise an estimate from an RNG
    seeded with ``seed``, so the same situation always shows the same numbers.
    """
    if len(hands) < 2:
        raise ValueError("Equity needs at least two hands.")

    exact = BOARD_SIZE - len(board) <= MAX_EXACT_CARDS_TO_COME
    calculator = EquityCalculator(
        hands, board, seed=seed, exact_limit=math.inf if exact else 0
    )
    estimate_boards = max(1, ESTIMATE_EVALUATIONS // len(hands))
    calculator.run(calculator.total_boards or estimate_boards)

    return Equity(shares=calculator.result().equity, exact=calculator.exact)
