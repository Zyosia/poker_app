"""Heads-up push/fold solved by counterfactual regret minimization (CFR+).

**The game.** Two players, an effective stack of ``S`` big blinds, antes
possible (V2.x).
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

The solutions the bots use, heads-up here and three-handed
(``three_handed_solver``), for no ante, classic antes and a big-blind ante,
are precomputed in ``push_fold_solutions``, because solving takes a while.
Regenerate them (about 15 minutes on 6 cores) with::

    python -m backend.bots.push_fold_solver
"""

import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor
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
"""Effective stacks (big blinds) of the precomputed heads-up solutions."""
THREE_HANDED_DEPTHS: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20)
"""Effective stacks of the three-handed solutions (the nearest is played)."""
THREE_HANDED_ITERATIONS = 1_000_000
HEADS_UP_ANTES: dict[str, tuple[float, float]] = {
    "none": (0.0, 0.0),
    "classic": (0.1, 0.1),
    "big_blind": (0.0, 1.0),
}
"""Antes in big blinds, small blind then big blind: the application's
classic antes are a tenth of the big blind, its big-blind ante a big blind."""
THREE_HANDED_ANTES: dict[str, tuple[float, float, float]] = {
    "none": (0.0, 0.0, 0.0),
    "classic": (0.1, 0.1, 0.1),
    "big_blind": (0.0, 0.0, 1.0),
}
SOLUTION_SAMPLES = 400
"""Random boards per pair of hands for the precomputed equities."""
SOLUTION_ITERATIONS = 600
SOLUTION_SEED = 20261117
IN_RANGE = 0.5
"""A hand belongs to a range when it is played at least this often."""
SOLUTION_MODULE = Path(__file__).with_name("push_fold_solutions.py")

SINGLE_LINE = 88 - 12 - 3
"""The longest range kept on one line of the generated module."""

Matrix = list[list[float]]
DECK: tuple[Card, ...] = tuple(rank + suit for rank in RANKS for suit in SUITS)


@dataclass(frozen=True)
class PushFoldStrategy:
    """How often each starting hand shoves (small blind) or calls (big blind)."""

    stack: float
    push: tuple[float, ...]
    call: tuple[float, ...]
    antes: tuple[float, float] = (0.0, 0.0)
    """The small blind's and the big blind's antes, in big blinds."""

    @property
    def posted(self) -> tuple[float, float]:
        """What each player loses by folding: blind and ante."""
        return SMALL_BLIND + self.antes[0], BIG_BLIND + self.antes[1]

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
    call: list[float],
    equity: Matrix,
    weights: Matrix,
    stack: float,
    big_blind_posted: float = BIG_BLIND,
) -> list[float]:
    """The small blind's average result (big blinds) when shoving each hand;
    a fold of the big blind wins what it posted (blind and ante)."""
    values = []

    for row_equity, row_weights in zip(equity, weights, strict=True):
        total = 0.0
        weight = 0.0

        for eq, w, c in zip(row_equity, row_weights, call, strict=True):
            total += w * (c * stack * (2 * eq - 1) + (1 - c) * big_blind_posted)
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
    equity: Matrix,
    weights: Matrix,
    stack: float,
    iterations: int,
    antes: tuple[float, float] = (0.0, 0.0),
) -> PushFoldStrategy:
    """CFR+ with alternating updates and a linearly weighted average.

    ``antes`` are the small blind's and the big blind's antes in big blinds
    (both 0.1 with classic antes; (0, 1) with a big-blind ante). Each stack
    holds ``stack`` big blinds before the blinds and antes are posted.
    """
    small_blind_posted = SMALL_BLIND + antes[0]
    big_blind_posted = BIG_BLIND + antes[1]
    size = len(HANDS)
    push_regret = [[0.0, 0.0] for _ in range(size)]  # [push, fold]
    call_regret = [[0.0, 0.0] for _ in range(size)]  # [call, fold]
    push_sum = [0.0] * size
    call_sum = [0.0] * size
    weight_sum = 0.0

    for iteration in range(1, iterations + 1):
        push = _regret_matching(push_regret)
        call = _regret_matching(call_regret)
        values = push_values(call, equity, weights, stack, big_blind_posted)

        for i, value in enumerate(values):
            average = push[i] * value + (1 - push[i]) * -small_blind_posted
            regret = push_regret[i]
            regret[0] = max(0.0, regret[0] + value - average)
            regret[1] = max(0.0, regret[1] - small_blind_posted - average)

        push = _regret_matching(push_regret)
        values = call_values(push, equity, weights, stack)

        for j, value in enumerate(values):
            average = call[j] * value + (1 - call[j]) * -big_blind_posted
            regret = call_regret[j]
            regret[0] = max(0.0, regret[0] + value - average)
            regret[1] = max(0.0, regret[1] - big_blind_posted - average)

        call = _regret_matching(call_regret)
        weight_sum += iteration

        for i in range(size):
            push_sum[i] += iteration * push[i]
            call_sum[i] += iteration * call[i]

    return PushFoldStrategy(
        stack=stack,
        push=tuple(p / weight_sum for p in push_sum),
        call=tuple(c / weight_sum for c in call_sum),
        antes=antes,
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
    small_blind_posted, big_blind_posted = strategy.posted
    hand_weights = [sum(row) for row in weights]
    total = sum(hand_weights)

    def average(values: list[float]) -> float:
        return sum(w * v for w, v in zip(hand_weights, values, strict=True)) / total

    shove = push_values(call, equity, weights, stack, big_blind_posted)
    small_blind_now = average(
        [
            p * v + (1 - p) * -small_blind_posted
            for p, v in zip(push, shove, strict=True)
        ]
    )
    small_blind_best = average([max(v, -small_blind_posted) for v in shove])

    called = call_values(push, equity, weights, stack)
    reach = _shove_reach(push, weights)
    big_blind_now = (
        sum(
            r * (c * v + (1 - c) * -big_blind_posted)
            for r, c, v in zip(reach, call, called, strict=True)
        )
        / total
    )
    big_blind_best = (
        sum(r * max(v, -big_blind_posted) for r, v in zip(reach, called, strict=True))
        / total
    )

    return ((small_blind_best - small_blind_now) + (big_blind_best - big_blind_now)) / 2


def _shove_reach(push: list[float], weights: Matrix) -> list[float]:
    """Weight of the shoves each big blind hand faces."""
    size = len(push)

    return [sum(weights[i][j] * push[i] for i in range(size)) for j in range(size)]


# --- The precomputed solution ------------------------------------------------------


HeadsUpRanges = dict[str, dict[int, tuple[str, str]]]
ThreeHandedRanges = dict[str, dict[int, tuple[str, ...]]]


def write_solution(path: Path = SOLUTION_MODULE, workers: int | None = None) -> None:
    """Solve every ante and depth, heads-up and three-handed, in parallel,
    and write the ranges as a module."""
    from .three_handed_solver import Spot, solve_three_handed

    with ProcessPoolExecutor(workers or os.cpu_count()) as pool:
        three_handed = {
            (kind, depth): pool.submit(
                solve_three_handed,
                depth,
                THREE_HANDED_ITERATIONS,
                SOLUTION_SEED + depth,
                antes,
            )
            for kind, antes in THREE_HANDED_ANTES.items()
            for depth in THREE_HANDED_DEPTHS
        }
        weights = combo_pair_counts()
        equity = equity_matrix(SOLUTION_SAMPLES, SOLUTION_SEED)
        heads_up = {
            (kind, depth): pool.submit(
                solve, equity, weights, depth, SOLUTION_ITERATIONS, antes
            )
            for kind, antes in HEADS_UP_ANTES.items()
            for depth in DEPTHS
        }
        heads_up_ranges: HeadsUpRanges = {kind: {} for kind in HEADS_UP_ANTES}

        for (kind, depth), future in heads_up.items():
            strategy = future.result()
            gap = exploitability(strategy, equity, weights)
            print(f"heads-up {kind} {depth:>2} bb: {gap:.2e} bb", file=sys.stderr)
            heads_up_ranges[kind][depth] = (
                range_notation(strategy.push_range()),
                range_notation(strategy.call_range()),
            )

        three_ranges: ThreeHandedRanges = {kind: {} for kind in THREE_HANDED_ANTES}

        for (kind, depth), future in three_handed.items():
            solved = future.result()
            print(f"three-handed {kind} {depth:>2} bb", file=sys.stderr)
            three_ranges[kind][depth] = tuple(
                range_notation(solved.range_at(spot)) for spot in Spot
            )

    path.write_text(solution_source(heads_up_ranges, three_ranges), encoding="utf-8")


def solution_source(heads_up: HeadsUpRanges, three_handed: ThreeHandedRanges) -> str:
    """The source of the ``push_fold_solutions`` module."""
    lines = [
        '"""Push/fold ranges at equilibrium, by ante and effective stack.',
        "",
        "Generated by ``python -m backend.bots.push_fold_solver``; do not edit by",
        "hand. Heads-up: CFR+, "
        f"{SOLUTION_ITERATIONS} iterations, equities from {SOLUTION_SAMPLES} random",
        f"boards per pair of hands. Three-handed: Monte Carlo CFR, "
        f"{THREE_HANDED_ITERATIONS:,} deals.",
        f"Seed {SOLUTION_SEED}. Antes: none, classic (a tenth of the big blind each)",
        "or big blind (the big blind posts one big blind).",
        "",
        "HEADS_UP_RANGES[ante][depth]: (small blind shoves, big blind calls).",
        "THREE_HANDED_RANGES[ante][depth]: (button shoves, small blind calls the",
        "button, small blind shoves, big blind calls the button, big blind calls",
        "both, big blind calls the small blind).",
        '"""',
        "",
        "HEADS_UP_RANGES: dict[str, dict[int, tuple[str, str]]] = {",
    ]
    lines += _table(heads_up)
    lines.append("}")
    lines.append("")
    lines.append("THREE_HANDED_RANGES: dict[str, dict[int, tuple[str, ...]]] = {")
    lines += _table(three_handed)
    lines.append("}")

    return "\n".join(lines) + "\n"


def _table(solutions: dict[str, dict[int, tuple[str, ...]]]) -> list[str]:
    lines: list[str] = []

    for kind, depths in solutions.items():
        lines.append(f'    "{kind}": {{')

        for depth, ranges in depths.items():
            lines.append(f"        {depth}: (")

            for notation in ranges:
                lines += _wrapped(notation)

            lines.append("        ),")

        lines.append("    },")

    return lines


def _wrapped(notation: str, width: int = 66) -> list[str]:
    """A notation as implicitly joined string lines, then a comma."""
    if len(notation) <= SINGLE_LINE:  # As the formatter would keep it.
        return [f'{" " * 12}"{notation}",']

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
    indent = " " * 12

    if len(lines) == 1:
        return [f'{indent}"{lines[0]}",']

    return [f'{indent}"{text}"' for text in lines[:-1]] + [f'{indent}"{lines[-1]}",']


if __name__ == "__main__":
    write_solution()
