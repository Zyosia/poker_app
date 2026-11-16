"""Push/fold ranges by stack depth and position, for short stacks.

A range is the strongest X% of starting hands, counted in combinations (a
pair has 6, a suited hand 4, an offsuit hand 12, 1326 in all).

**Where the hand order comes from.** ``HAND_ORDER`` ranks the 169 starting
hands by their all-in equity against one random hand, which is the usual
ordering behind push/fold charts. It was computed with this project's own
hand evaluator (``evaluate_rank``): a Monte Carlo of 30,000 random opponent
hands and boards per starting hand, seed 20261116. Hands whose equities are
within the Monte Carlo noise (about 0.3%) may swap places; that does not
matter at the precision of these ranges.

**The percentages** (``OPEN_SHOVE_PERCENT``, ``CALL_SHOVE_PERCENT``) are
simplified approximations of standard Nash push/fold charts for 6-max
tables: wider with shorter stacks and later positions, and calling ranges
tighter than shoving ranges. Each bot profile scales them to keep its style.
Between two depths of a table, the percentage is interpolated linearly.
"""

from backend.poker_engine.constants import RANKS, Card, Position

HAND_ORDER: tuple[str, ...] = (
    "AA",
    "KK",
    "QQ",
    "JJ",
    "TT",
    "99",
    "88",
    "AKs",
    "77",
    "AQs",
    "AJs",
    "AKo",
    "ATs",
    "AQo",
    "AJo",
    "66",
    "ATo",
    "KQs",
    "A9s",
    "KJs",
    "A8s",
    "KTs",
    "KQo",
    "A7s",
    "A9o",
    "QJs",
    "55",
    "A8o",
    "KTo",
    "A5s",
    "KJo",
    "QTs",
    "K9s",
    "A6s",
    "A7o",
    "A4s",
    "K8s",
    "QJo",
    "K9o",
    "A3s",
    "K7s",
    "QTo",
    "A6o",
    "JTs",
    "A5o",
    "A2s",
    "44",
    "Q9s",
    "A4o",
    "K6s",
    "K8o",
    "J9s",
    "JTo",
    "A3o",
    "Q8s",
    "K7o",
    "Q9o",
    "K5s",
    "K4s",
    "A2o",
    "Q7s",
    "T9s",
    "K6o",
    "J8s",
    "K3s",
    "Q8o",
    "K5o",
    "33",
    "Q6s",
    "J9o",
    "K2s",
    "Q5s",
    "T8s",
    "Q7o",
    "K4o",
    "K3o",
    "Q4s",
    "J7s",
    "J8o",
    "Q3s",
    "T9o",
    "J6s",
    "Q6o",
    "K2o",
    "J5s",
    "Q5o",
    "T7s",
    "98s",
    "J7o",
    "22",
    "Q2s",
    "T8o",
    "Q4o",
    "97s",
    "J4s",
    "98o",
    "Q3o",
    "J3s",
    "J6o",
    "T6s",
    "T7o",
    "87s",
    "J2s",
    "T5s",
    "96s",
    "Q2o",
    "J5o",
    "T6o",
    "97o",
    "86s",
    "J4o",
    "T4s",
    "T3s",
    "76s",
    "95s",
    "J3o",
    "87o",
    "T2s",
    "J2o",
    "T5o",
    "96o",
    "85s",
    "94s",
    "75s",
    "T4o",
    "84s",
    "86o",
    "93s",
    "65s",
    "95o",
    "76o",
    "T3o",
    "92s",
    "T2o",
    "74s",
    "54s",
    "64s",
    "85o",
    "94o",
    "75o",
    "83s",
    "82s",
    "73s",
    "93o",
    "65o",
    "84o",
    "53s",
    "63s",
    "92o",
    "43s",
    "54o",
    "74o",
    "64o",
    "72s",
    "62s",
    "52s",
    "83o",
    "42s",
    "73o",
    "82o",
    "53o",
    "63o",
    "32s",
    "43o",
    "72o",
    "62o",
    "52o",
    "42o",
    "32o",
)

DEPTHS: tuple[float, ...] = (3, 5, 8, 10, 12, 15, 20, 25)
"""Effective stacks, in big blinds, of the columns of the tables below."""

# Strongest X% of hands shoved first in, by position (the button is the
# small blind heads-up). The big blind shoves over limpers.
OPEN_SHOVE_PERCENT: dict[Position, tuple[float, ...]] = {
    Position.UTG: (40, 26, 18, 15, 13, 11, 9, 8),
    Position.HJ: (45, 30, 21, 18, 15, 13, 11, 9),
    Position.CO: (55, 38, 28, 24, 20, 17, 14, 12),
    Position.BTN: (65, 50, 38, 33, 28, 24, 19, 16),
    Position.SB: (80, 65, 52, 45, 40, 35, 28, 22),
    Position.BB: (65, 50, 38, 33, 28, 24, 19, 16),
}

# Strongest X% of hands calling an all-in (or re-shoving over a raise).
CALL_SHOVE_PERCENT: dict[str, tuple[float, ...]] = {
    "big_blind": (60, 42, 30, 25, 21, 17, 13, 10),
    "other": (40, 26, 17, 14, 12, 10, 8, 6.5),
}

MULTIWAY_FACTOR = 0.5
"""Calling ranges halve when another player is already in the pot."""

COMBINATIONS = 1326


def hand_class(hole_cards: tuple[Card, ...]) -> str:
    """The class of two hole cards: "AA", "AKs" or "AKo"."""
    high, low = sorted(hole_cards, key=lambda card: RANKS.index(card[0]), reverse=True)

    if high[0] == low[0]:
        return high[0] + low[0]

    suited = "s" if high[1] == low[1] else "o"

    return high[0] + low[0] + suited


def combinations(hand: str) -> int:
    if len(hand) == 2:
        return 6

    return 4 if hand.endswith("s") else 12


def _percent_before() -> dict[str, float]:
    """Share of the combinations stronger than each hand, in percent."""
    result: dict[str, float] = {}
    before = 0

    for hand in HAND_ORDER:
        result[hand] = before * 100 / COMBINATIONS
        before += combinations(hand)

    return result


PERCENT_BEFORE = _percent_before()


def in_top_percent(hole_cards: tuple[Card, ...], percent: float) -> bool:
    """True if the hand is among the strongest ``percent`` of hands.

    A hand belongs to the range as soon as the range reaches it, so the best
    hand (aces) is in any range above 0%.
    """
    return PERCENT_BEFORE[hand_class(hole_cards)] < percent


def open_shove_percent(position: Position, depth: float) -> float:
    return _interpolate(OPEN_SHOVE_PERCENT[position], depth)


def call_shove_percent(is_big_blind: bool, depth: float, multiway: bool) -> float:
    table = CALL_SHOVE_PERCENT["big_blind" if is_big_blind else "other"]
    percent = _interpolate(table, depth)

    return percent * MULTIWAY_FACTOR if multiway else percent


def _interpolate(values: tuple[float, ...], depth: float) -> float:
    if depth <= DEPTHS[0]:
        return values[0]

    for index in range(1, len(DEPTHS)):
        if depth <= DEPTHS[index]:
            low, high = DEPTHS[index - 1], DEPTHS[index]
            share = (depth - low) / (high - low)

            return values[index - 1] + share * (values[index] - values[index - 1])

    return values[-1]
