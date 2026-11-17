"""Heads-up push/fold solved by counterfactual regret minimization (CFR+).

**The game.** Two players, no ante, an effective stack of ``S`` big blinds.
The small blind (the button) either shoves all-in or folds; facing a shove,
the big blind calls or folds. It is the end game of every heads-up
tournament (the last two players of a Spin & Go), and it is small enough to
be solved exactly: 169 starting hands per player, two actions each.

**The method.** Each player's strategy is a probability of shoving (or
calling) per starting hand. CFR+ plays the game against itself over and over:
after each pass, every hand adds the gain it would have had with the other
action to its *regret*, and plays the actions in proportion to their positive
regret. The average strategy converges to a Nash equilibrium: neither player
can gain by changing their ranges. ``exploitability`` measures how far from
it a pair of strategies is.

**The equities** between starting hands come from ``equity_matrix``: a Monte
Carlo of random suits and boards per pair of hands, with this project's own
hand evaluator. Card removal is exact: each pair of hands weighs the number
of combinations that do not share a card (``combo_pair_counts``).

The solution the bots use is precomputed in ``heads_up_push_fold``, because
solving takes minutes. Regenerate it with::

    python -m backend.bots.push_fold_solver
"""

import random
import sys
from dataclasses import dataclass
from pathlib import Path

from backend.application.ranges import ALL_LABELS, label_combos, range_notation
from backend.poker_engine.constants import RANKS, SUITS, Card
from backend.poker_engine.hand_evaluator import evaluate_rank

HANDS: tuple[str, ...] = ALL_LABELS
"""The 169 starting hands, in the order of every list of this module."""
SMALL_BLIND = 0.5
BIG_BLIND = 1.0
DEPTHS: tuple[int, ...] = tuple(range(1, 21))
"""Effective stacks (big blinds) of the precomputed solution."""
SOLUTION_SAMPLES = 400
"""Random boards per pair of hands for the precomputed equities."""
SOLUTION_ITERATIONS = 600
SOLUTION_SEED = 20261117
IN_RANGE = 0.5
"""A hand belongs to a range when it is played at least this often."""
SOLUTION_MODULE = Path(__file__).with_name("heads_up_push_fold.py")

Matrix = list[list[float]]
DECK: tuple[Card, ...] = tuple(rank + suit for rank in RANKS for suit in SUITS)


@dataclass(frozen=True)
class PushFoldStrategy:
    """How often each starting hand shoves (small blind) or calls (big blind)."""

    stack: float
    push: tuple[float, ...]
    call: tuple[float, ...]

    def push_range(self) -> frozenset[str]:
        return frozenset(
            h for h, p in zip(HANDS, self.push, strict=True) if p >= IN_RANGE
        )

    def call_range(self) -> frozenset[str]:
        return frozenset(
            h for h, p in zip(HANDS, self.call, strict=True) if p >= IN_RANGE
        )


# --- Equities ----------------------------------------------------------------------


def combo_pair_counts() -> Matrix:
    """Pairs of combinations of two hands that share no card."""
    combos = [label_combos(hand) for hand in HANDS]

    return [
        [
            float(sum(1 for a in first for b in second if not set(a) & set(b)))
            for second in combos
        ]
        for first in combos
    ]


def equity_matrix(samples: int, seed: int) -> Matrix:
    """``matrix[i][j]``: the all-in equity of hand ``i`` against hand ``j``.

    Every unordered pair draws ``samples`` random deals (suits and board);
    ties count half.
    """
    rng = random.Random(seed)
    combos = [label_combos(hand) for hand in HANDS]
    size = len(HANDS)
    matrix = [[0.5] * size for _ in range(size)]

    for i in range(size):
        for j in range(i, size):
            share = _sampled_equity(combos[i], combos[j], samples, rng)
            matrix[i][j] = share
            matrix[j][i] = 1.0 - share

    return matrix


def _sampled_equity(
    first: tuple[tuple[Card, Card], ...],
    second: tuple[tuple[Card, Card], ...],
    samples: int,
    rng: random.Random,
) -> float:
    pairs = [(a, b) for a in first for b in second if not set(a) & set(b)]
    points = 0.0

    for _ in range(samples):
        a, b = rng.choice(pairs)
        used = {*a, *b}
        board = rng.sample(DECK, 9)
        board = [card for card in board if card not in used][:5]
        mine = evaluate_rank([*a, *board])
        theirs = evaluate_rank([*b, *board])
        points += 1.0 if mine > theirs else 0.5 if mine == theirs else 0.0

    return points / samples


# --- Values ------------------------------------------------------------------------


def push_values(
    call: list[float], equity: Matrix, weights: Matrix, stack: float
) -> list[float]:
    """The small blind's average result (big blinds) when shoving each hand."""
    values = []

    for row_equity, row_weights in zip(equity, weights, strict=True):
        total = 0.0
        weight = 0.0

        for eq, w, c in zip(row_equity, row_weights, call, strict=True):
            total += w * (c * stack * (2 * eq - 1) + (1 - c) * BIG_BLIND)
            weight += w

        values.append(total / weight)

    return values


def call_values(
    push: list[float], equity: Matrix, weights: Matrix, stack: float
) -> list[float]:
    """The big blind's result of calling with each hand, against the
    shoves; folding loses the big blind against the same shoves."""
    size = len(push)
    values = [0.0] * size
    reach = [0.0] * size

    for i, (row_equity, row_weights) in enumerate(zip(equity, weights, strict=True)):
        shove = push[i]

        if shove == 0:
            continue

        for j in range(size):
            w = row_weights[j] * shove
            values[j] += w * stack * (1 - 2 * row_equity[j])
            reach[j] += w

    return [v / r if r else 0.0 for v, r in zip(values, reach, strict=True)]


# --- Solving -----------------------------------------------------------------------


def solve(
    equity: Matrix, weights: Matrix, stack: float, iterations: int
) -> PushFoldStrategy:
    """CFR+ with alternating updates and a linearly weighted average."""
    size = len(HANDS)
    push_regret = [[0.0, 0.0] for _ in range(size)]  # [push, fold]
    call_regret = [[0.0, 0.0] for _ in range(size)]  # [call, fold]
    push_sum = [0.0] * size
    call_sum = [0.0] * size
    weight_sum = 0.0

    for iteration in range(1, iterations + 1):
        push = _regret_matching(push_regret)
        call = _regret_matching(call_regret)
        values = push_values(call, equity, weights, stack)

        for i, value in enumerate(values):
            average = push[i] * value + (1 - push[i]) * -SMALL_BLIND
            regret = push_regret[i]
            regret[0] = max(0.0, regret[0] + value - average)
            regret[1] = max(0.0, regret[1] - SMALL_BLIND - average)

        push = _regret_matching(push_regret)
        values = call_values(push, equity, weights, stack)

        for j, value in enumerate(values):
            average = call[j] * value + (1 - call[j]) * -BIG_BLIND
            regret = call_regret[j]
            regret[0] = max(0.0, regret[0] + value - average)
            regret[1] = max(0.0, regret[1] - BIG_BLIND - average)

        call = _regret_matching(call_regret)
        weight_sum += iteration

        for i in range(size):
            push_sum[i] += iteration * push[i]
            call_sum[i] += iteration * call[i]

    return PushFoldStrategy(
        stack=stack,
        push=tuple(p / weight_sum for p in push_sum),
        call=tuple(c / weight_sum for c in call_sum),
    )


def _regret_matching(regrets: list[list[float]]) -> list[float]:
    """The probability of the first action, in proportion to positive regret."""
    return [
        first / (first + second) if first + second > 0 else 0.5
        for first, second in regrets
    ]


def exploitability(
    strategy: PushFoldStrategy, equity: Matrix, weights: Matrix
) -> float:
    """What best responses win against the strategy, in big blinds per hand
    on average over both seats; 0 at a Nash equilibrium."""
    stack = strategy.stack
    push = list(strategy.push)
    call = list(strategy.call)
    hand_weights = [sum(row) for row in weights]
    total = sum(hand_weights)

    def average(values: list[float]) -> float:
        return sum(w * v for w, v in zip(hand_weights, values, strict=True)) / total

    shove = push_values(call, equity, weights, stack)
    small_blind_now = average(
        [p * v + (1 - p) * -SMALL_BLIND for p, v in zip(push, shove, strict=True)]
    )
    small_blind_best = average([max(v, -SMALL_BLIND) for v in shove])

    called = call_values(push, equity, weights, stack)
    reach = _shove_reach(push, weights)
    big_blind_now = (
        sum(
            r * (c * v + (1 - c) * -BIG_BLIND)
            for r, c, v in zip(reach, call, called, strict=True)
        )
        / total
    )
    big_blind_best = (
        sum(r * max(v, -BIG_BLIND) for r, v in zip(reach, called, strict=True)) / total
    )

    return ((small_blind_best - small_blind_now) + (big_blind_best - big_blind_now)) / 2


def _shove_reach(push: list[float], weights: Matrix) -> list[float]:
    """Weight of the shoves each big blind hand faces."""
    size = len(push)

    return [sum(weights[i][j] * push[i] for i in range(size)) for j in range(size)]


# --- The precomputed solution ------------------------------------------------------


def write_solution(path: Path = SOLUTION_MODULE) -> None:
    """Solve every depth of ``DEPTHS`` and write the ranges as a module."""
    weights = combo_pair_counts()
    equity = equity_matrix(SOLUTION_SAMPLES, SOLUTION_SEED)
    solution: dict[int, tuple[str, str]] = {}

    for depth in DEPTHS:
        strategy = solve(equity, weights, depth, SOLUTION_ITERATIONS)
        gap = exploitability(strategy, equity, weights)
        print(f"{depth:>2} bb: exploitability {gap:.2e} bb", file=sys.stderr)
        solution[depth] = (
            range_notation(strategy.push_range()),
            range_notation(strategy.call_range()),
        )

    path.write_text(solution_source(solution), encoding="utf-8")


def solution_source(solution: dict[int, tuple[str, str]]) -> str:
    """The source of the ``heads_up_push_fold`` module."""
    lines = [
        '"""Heads-up push/fold ranges at equilibrium, by effective stack.',
        "",
        "Generated by ``python -m backend.bots.push_fold_solver`` (CFR+,",
        f"{SOLUTION_ITERATIONS} iterations, equities from {SOLUTION_SAMPLES} random",
        f"boards per pair of hands, seed {SOLUTION_SEED}); do not edit by hand. No",
        "ante. Each depth maps to (small blind shoving range, big blind calling",
        "range).",
        '"""',
        "",
        "PUSH_FOLD_RANGES: dict[int, tuple[str, str]] = {",
    ]

    for depth, ranges in solution.items():
        lines.append(f"    {depth}: (")

        for notation in ranges:
            lines += _wrapped(notation)

        lines.append("    ),")

    lines.append("}")

    return "\n".join(lines) + "\n"


def _wrapped(notation: str, width: int = 70) -> list[str]:
    """A notation as implicitly joined string lines, then a comma."""
    hands = notation.split(", ") if notation else []
    lines: list[str] = []
    line = ""

    for index, hand in enumerate(hands):
        piece = hand if index == len(hands) - 1 else hand + ", "

        if line and len(line) + len(piece.rstrip()) > width:
            lines.append(line)
            line = ""

        line += piece

    lines.append(line)
    indent = " " * 8

    if len(lines) == 1:
        return [f'{indent}"{lines[0]}",']

    return [f'{indent}"{text}"' for text in lines[:-1]] + [f'{indent}"{lines[-1]}",']


if __name__ == "__main__":
    write_solution()
