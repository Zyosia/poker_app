"""Hand ranges: the 169 starting hands, range notation and preset ranges.

A range is a set of starting hands of the 13 × 13 grid: pairs on the
diagonal ("QQ"), suited hands above it ("AKs", 4 combinations each), offsuit
hands below it ("AKo", 12 combinations). Notation, as in common equity tools:

- ``QQ``, ``AKs``, ``AKo``, and ``AK`` for both suited and offsuit;
- ``QQ+`` (QQ to AA), ``A9s+`` (A9s to AKs), ``KTo+``, ``KT+``;
- ``22-55``, ``K9s-K6s``; hands separated by commas or spaces.

Every combination of a range counts the same (no weights).
"""

from dataclasses import dataclass
from functools import cache
from itertools import combinations

from backend.poker_engine.constants import RANKS, SUITS, Card

Combo = tuple[Card, Card]

GRID_RANKS = RANKS[::-1]
"""A to 2: the order of the grid's rows and columns."""
TOTAL_COMBOS = 1326


def grid_label(row: int, column: int) -> str:
    """The hand of a grid cell: pairs on the diagonal, suited above it."""
    high, low = GRID_RANKS[min(row, column)], GRID_RANKS[max(row, column)]

    if row == column:
        return high + low

    return high + low + ("s" if row < column else "o")


ALL_LABELS: tuple[str, ...] = tuple(
    grid_label(row, column) for row in range(13) for column in range(13)
)


@cache
def label_combos(label: str) -> tuple[Combo, ...]:
    """The combinations of one starting hand ("AKs": 4, "AKo": 12, "QQ": 6).

    Cached: 169 small tuples, read again and again by the bots' ranges."""
    high, low = label[0], label[1]

    if high == low:
        return tuple(
            (high + first, high + second) for first, second in combinations(SUITS, 2)
        )

    if label.endswith("s"):
        return tuple((high + suit, low + suit) for suit in SUITS)

    return tuple(
        (high + first, low + second)
        for first in SUITS
        for second in SUITS
        if first != second
    )


@dataclass(frozen=True)
class HandRange:
    """A set of starting hands."""

    labels: frozenset[str]

    @classmethod
    def parse(cls, text: str) -> "HandRange":
        return cls(frozenset(parse_range(text)))

    def combos(self) -> tuple[Combo, ...]:
        return tuple(
            combo
            for label in ALL_LABELS
            if label in self.labels
            for combo in label_combos(label)
        )

    @property
    def combo_count(self) -> int:
        return sum(len(label_combos(label)) for label in self.labels)

    @property
    def share(self) -> float:
        """Share of all 1,326 starting combinations."""
        return self.combo_count / TOTAL_COMBOS

    @property
    def notation(self) -> str:
        return range_notation(self.labels)


ANY_TWO = HandRange(frozenset(ALL_LABELS))


# --- Notation --------------------------------------------------------------------


def parse_range(text: str) -> set[str]:
    """The starting hands of a range written in notation; raises ValueError."""
    labels: set[str] = set()

    for token in text.replace(",", " ").split():
        labels |= _parse_token(token)

    return labels


def _parse_token(token: str) -> set[str]:
    original = token
    token = token.upper().replace("10", "T")
    plus = token.endswith("+")
    token = token.rstrip("+")

    if "-" in token:
        first, last = token.split("-", 1)
        return _span(_hand(first, original), _hand(last, original), original)

    hand = _hand(token, original)

    if not plus:
        return _expand(hand)

    high, low, kind = hand

    if high == low:  # QQ+: up to aces.
        return _span(hand, ("A", "A", kind), original)

    top_kicker = GRID_RANKS[GRID_RANKS.index(high) + 1]  # A9s+: up to AKs.

    return _span(hand, (high, top_kicker, kind), original)


def _hand(token: str, original: str) -> tuple[str, str, str]:
    """(high rank, low rank, "s" / "o" / "" for both)."""
    kind = ""

    if len(token) == 3 and token[2] in "SO":
        kind = token[2].lower()
        token = token[:2]

    if len(token) != 2 or token[0] not in RANKS or token[1] not in RANKS:
        raise ValueError(f"“{original}” is not a hand of a range (like AKs or QQ+).")

    high, low = sorted(token, key=GRID_RANKS.index)

    if high == low and kind:
        raise ValueError(f"“{original}”: a pair is neither suited nor offsuit.")

    return high, low, kind


def _expand(hand: tuple[str, str, str]) -> set[str]:
    high, low, kind = hand

    if high == low:
        return {high + low}

    kinds = [kind] if kind else ["s", "o"]

    return {high + low + k for k in kinds}


def _span(
    first: tuple[str, str, str], last: tuple[str, str, str], original: str
) -> set[str]:
    """Every hand from ``first`` to ``last``: pairs, or one high card's kickers."""
    if first[0] == first[1] and last[0] == last[1]:
        ranks = _between(first[0], last[0])
        return {rank + rank for rank in ranks}

    if first[0] != last[0] or first[2] != last[2] or first[0] in (first[1], last[1]):
        raise ValueError(
            f"“{original}” is not a span of hands (like K9s-K6s or 22-55)."
        )

    labels: set[str] = set()

    for kicker in _between(first[1], last[1]):
        labels |= _expand((first[0], kicker, first[2]))

    return labels


def _between(first: str, last: str) -> list[str]:
    start, end = sorted((GRID_RANKS.index(first), GRID_RANKS.index(last)))

    return list(GRID_RANKS[start : end + 1])


def range_notation(labels: frozenset[str] | set[str]) -> str:
    """The shortest usual notation of a set of hands ("TT+, A9s+, KQo")."""
    parts = _runs(
        [rank + rank for rank in GRID_RANKS if rank + rank in labels],
        top=f"{GRID_RANKS[0]}{GRID_RANKS[0]}",
    )

    for kind in ("s", "o"):
        for high_index, high in enumerate(GRID_RANKS[:-1]):
            kickers = [
                high + low + kind
                for low in GRID_RANKS[high_index + 1 :]
                if high + low + kind in labels
            ]
            parts += _runs(kickers, top=high + GRID_RANKS[high_index + 1] + kind)

    return ", ".join(parts)


def _runs(labels: list[str], top: str) -> list[str]:
    """Group hands that follow each other in the grid: "QQ+", "K9s-K6s"."""
    if not labels:
        return []

    order = [label for label in ALL_LABELS if label in labels]
    runs: list[list[str]] = []

    for label in order:
        if runs and _follows(runs[-1][-1], label):
            runs[-1].append(label)
        else:
            runs.append([label])

    texts = []

    for run in runs:
        if len(run) == 1:
            texts.append(run[0])
        elif run[0] == top:
            texts.append(_plus(run[-1]))
        else:
            texts.append(f"{run[0]}-{run[-1]}")

    return texts


def _plus(label: str) -> str:
    return f"{label}+"


def _follows(previous: str, label: str) -> bool:
    """True when ``label`` is the next hand down from ``previous``."""
    if previous[0] == previous[1]:
        return (
            label[0] == label[1]
            and GRID_RANKS.index(label[0]) == GRID_RANKS.index(previous[0]) + 1
        )

    return (
        label[0] == previous[0]
        and label[2:] == previous[2:]
        and GRID_RANKS.index(label[1]) == GRID_RANKS.index(previous[1]) + 1
    )


# --- Presets ---------------------------------------------------------------------

PRESET_RANGES: dict[str, str] = {
    "UTG open": "22+, A2s+, KTs+, QTs+, JTs, T9s, 98s, 87s, ATo+, KJo+",
    "HJ open": (
        "22+, A2s+, K8s+, Q9s+, J9s+, T9s, 98s, 87s, 76s, 65s, A9o+, KTo+, QTo+, JTo"
    ),
    "CO open": (
        "22+, A2s+, K5s+, Q8s+, J8s+, T8s+, 97s+, 86s+, 75s+, 65s, 54s, "
        "A7o+, A5o, K9o+, Q9o+, J9o+, T9o"
    ),
    "BTN open": (
        "22+, A2s+, K2s+, Q4s+, J6s+, T6s+, 96s+, 85s+, 74s+, 63s+, 53s+, 43s, "
        "A2o+, K7o+, Q8o+, J8o+, T8o+, 97o+, 87o"
    ),
    "SB open": (
        "22+, A2s+, K2s+, Q5s+, J7s+, T7s+, 96s+, 86s+, 75s+, 64s+, 54s, "
        "A2o+, K8o+, Q9o+, J9o+, T9o"
    ),
    "BB vs BTN open — call": (
        "22-99, A2s-AJs, K2s-KJs, Q2s-QJs, J4s-JTs, T6s-T9s, 96s+, 85s+, 74s+, "
        "63s+, 53s+, 43s, A2o-AJo, K7o-KJo, Q8o-QJo, J8o-JTo, T8o+, 97o+, 87o, 76o"
    ),
    "BB vs BTN open — 3-bet": (
        "TT+, AQs+, A5s-A3s, KQs, K9s, QTs, J9s, T8s, 76s, AQo+"
    ),
    "SB vs BTN open — 3-bet": "99+, ATs+, A5s-A2s, KTs+, QTs+, JTs, AJo+, KQo",
    "BTN vs CO open — 3-bet": "TT+, AJs+, A5s-A4s, KQs, KTs, QJs, JTs, AQo+",
    "BTN vs CO open — call": (
        "22-99, ATs-A6s, K9s-KJs, Q9s+, J9s+, T8s+, 97s+, 86s+, 75s+, 65s, 54s, "
        "AJo-ATo, KJo+, QJo"
    ),
    "Premium (top 3%)": "QQ+, AKs, AKo",
    "Any two": "22+, A2+, K2+, Q2+, J2+, T2+, 92+, 82+, 72+, 62+, 52+, 42+, 32",
}
"""Approximations of common 100 BB 6-max cash-game charts, to start from."""


def preset_range(name: str) -> HandRange:
    return HandRange.parse(PRESET_RANGES[name])
