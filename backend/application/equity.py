"""Win probabilities (equity) of poker hands.

Two uses:

- **The run-out** (V1.0.1, ``calculate_equity``): the chances of the hands
  face up while the board is dealt after an all-in. With two cards or fewer
  to come, every possible board is counted, so the result is exact. Before
  the flop (about 1.7 million boards) it is estimated from a capped number
  of random boards, so the table never stalls.
- **The equity calculator** (V1.1, ``EquityCalculator``): hands, ranges
  (V1.1.1) or random hands (the range of any two cards) on any board. Every
  combination of the ranges and every board is counted when there are few
  enough; otherwise random deals (Monte Carlo) are drawn, as many as the
  caller asks for, in steps. Every combination of the ranges that does not
  share a card with another hand or the board counts the same.

The random boards come from an RNG of their own, so the game's cards are
never affected, and the same seed always gives the same numbers. Only the
cards given are known: anyone else's cards count as unknown.
"""

import math
import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import combinations, product

from backend.poker_engine.constants import MAX_TABLE_SEATS, RANKS, SUITS, Card
from backend.poker_engine.hand_evaluator import evaluate_rank

from .ranges import ANY_TWO, Combo, HandRange

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
MAX_SAMPLE_ATTEMPTS = 10_000
"""Random draws of the ranges' combinations allowed for one deal."""

PlayerHand = Sequence[Card] | HandRange | None
"""Two cards, a range, or None (no cards) for a random hand."""
Deal = tuple[list[tuple[Card, ...]], Sequence[Card]]


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
    """Equity of 2 to 9 hands or ranges, on a board of 0 to 5 cards."""

    def __init__(
        self,
        hands: Sequence[PlayerHand],
        board: Sequence[Card] = (),
        seed: int | None = None,
        exact_limit: float = EXACT_BOARD_LIMIT,
    ) -> None:
        """Each hand is two cards, a ``HandRange``, or None (or no cards) for
        a random hand. ``seed`` drives the random deals; up to
        ``exact_limit`` deals (combinations × boards), every deal is counted.
        """
        if not 2 <= len(hands) <= MAX_TABLE_SEATS:
            raise ValueError(f"Equity needs 2 to {MAX_TABLE_SEATS} hands.")

        if len(board) > BOARD_SIZE:
            raise ValueError("A board has at most five cards.")

        fixed: list[tuple[Card, ...] | None] = []
        ranges: list[HandRange] = []

        for hand in hands:
            if isinstance(hand, HandRange):
                ranges.append(hand)
                fixed.append(None)
            elif hand:
                if len(hand) != HOLE_CARDS:
                    raise ValueError("A hand has two cards, or none for a random hand.")

                fixed.append(tuple(hand))
            else:
                ranges.append(ANY_TWO)
                fixed.append(None)

        known = [card for hand in fixed if hand for card in hand] + list(board)
        known_set = set(known)

        if not known_set <= set(FULL_DECK):
            raise ValueError("Unknown card.")

        if len(known_set) != len(known):
            raise ValueError("A card appears twice.")

        self._fixed = fixed
        self._ranged = [index for index, hand in enumerate(fixed) if hand is None]
        self._choices: list[list[Combo]] = []

        for index, hand_range in zip(self._ranged, ranges, strict=True):
            combos = [
                combo
                for combo in hand_range.combos()
                if combo[0] not in known_set and combo[1] not in known_set
            ]

            if not combos:
                raise ValueError(
                    f"Hand {index + 1}: no combination of its range is left "
                    "with the cards chosen."
                )

            self._choices.append(combos)

        self._board = list(board)
        self._remaining = [card for card in FULL_DECK if card not in known_set]
        self._to_come = BOARD_SIZE - len(board)
        boards = math.comb(
            len(self._remaining) - HOLE_CARDS * len(self._ranged), self._to_come
        )
        bound = math.prod(len(choices) for choices in self._choices) * boards
        self.exact = bound <= exact_limit
        self.total_boards: int | None = None
        """Every possible deal, when they are all counted."""
        self._deals: Iterator[Deal] = iter(())

        if self.exact:
            assignments = [
                picked for picked in product(*self._choices) if _disjoint(picked)
            ]

            if not assignments:
                raise ValueError("The ranges have no combination left together.")

            self.total_boards = len(assignments) * boards
            self._deals = self._exact_deals(assignments)
        elif not self._has_assignment(0, set()):
            raise ValueError("The ranges have no combination left together.")

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

    def _deal(self) -> Deal | None:
        """The hands and the cards to come of the next deal; None at the end."""
        if self.exact:
            return next(self._deals, None)

        if not self._ranged:
            return self._hands_with(()), self._rng.sample(
                self._remaining, self._to_come
            )

        picked = self._sample_assignment()
        used = {card for combo in picked for card in combo}
        rest = [card for card in self._remaining if card not in used]

        return self._hands_with(picked), self._rng.sample(rest, self._to_come)

    def _hands_with(self, picked: Sequence[Combo]) -> list[tuple[Card, ...]]:
        """Every hand, the ranges' ones taken from ``picked`` in order."""
        chosen = iter(picked)

        return [hand if hand is not None else next(chosen) for hand in self._fixed]

    def _exact_deals(self, assignments: list[tuple[Combo, ...]]) -> Iterator[Deal]:
        for picked in assignments:
            used = {card for combo in picked for card in combo}
            rest = [card for card in self._remaining if card not in used]
            hands = self._hands_with(picked)

            for runout in combinations(rest, self._to_come):
                yield hands, runout

    def _sample_assignment(self) -> tuple[Combo, ...]:
        """One combination per range, drawn uniformly among those that do not
        share a card (a draw that shares one is drawn again)."""
        choice = self._rng.choice

        for _ in range(MAX_SAMPLE_ATTEMPTS):
            picked = tuple(choice(choices) for choices in self._choices)

            if _disjoint(picked):
                return picked

        raise RuntimeError("The ranges hardly ever fit together; narrow them down.")

    def _has_assignment(self, index: int, used: set[Card]) -> bool:
        """True if the ranges from ``index`` on can avoid ``used`` and
        each other."""
        if index == len(self._choices):
            return True

        return any(
            self._has_assignment(index + 1, used | set(combo))
            for combo in self._choices[index]
            if not used & set(combo)
        )

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


def _disjoint(combos: Sequence[Combo]) -> bool:
    cards = [card for combo in combos for card in combo]

    return len(set(cards)) == len(cards)


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
