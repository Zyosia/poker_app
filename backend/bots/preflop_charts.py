"""Pre-flop ranges by position, for the strategy bots.

**Opening ranges.** The hands raised first in, by the number of players
still to act behind (the blinds included): the fewer players behind, the
fewer who can wake up with a better hand, so the wider the range. They are
simplified versions of common 6-max and full-ring opening charts: from about
9% of hands under the gun of a full ring to about 45% on the button, and 80%
for the small blind heads-up.

**Answers to a raise** use the share of the opener's range: against a wide
range (a button steal) it pays to re-raise and defend more. The big blind
defends wider (it already has a big blind in and closes the action); the
small blind does not flat-call (out of position for the whole hand), it
re-raises or folds. Hands are ranked by ``push_fold.HAND_ORDER`` (all-in
equity against a random hand).
"""

from functools import cache

from backend.application.ranges import HandRange
from backend.poker_engine.constants import Card, Position

from .push_fold import PERCENT_BEFORE, hand_class

PREFLOP_ORDER: tuple[Position, ...] = (
    Position.UTG,
    Position.UTG1,
    Position.UTG2,
    Position.LJ,
    Position.HJ,
    Position.CO,
    Position.BTN,
    Position.SB,
    Position.BB,
)
"""The order of the pre-flop action (heads-up, the button acts first)."""

OPEN_RANGES: dict[int, str] = {
    8: "77+, ATs+, KTs+, QJs, AJo+, KQo",
    7: "66+, A9s+, KTs+, QTs+, JTs, AJo+, KQo",
    6: "55+, A7s+, A5s, K9s+, QTs+, JTs, T9s, ATo+, KQo",
    5: "44+, A2s+, K9s+, Q9s+, J9s+, T9s, 98s, ATo+, KJo+",
    4: "33+, A2s+, K8s+, Q9s+, J9s+, T8s+, 98s, 87s, 76s, A9o+, KTo+, QJo",
    3: (
        "22+, A2s+, K6s+, Q8s+, J8s+, T8s+, 97s+, 86s+, 75s+, 65s, 54s, A7o+, A5o,"
        " KTo+, QTo+, JTo"
    ),
    2: (
        "22+, A2s+, K2s+, Q5s+, J7s+, T7s+, 96s+, 85s+, 74s+, 64s+, 53s+, 43s, A2o+,"
        " K8o+, Q9o+, J9o+, T9o, 98o"
    ),
    1: (
        "22+, A2s+, K2s+, Q4s+, J6s+, T6s+, 96s+, 85s+, 74s+, 63s+, 53s+, 43s, A2o+,"
        " K7o+, Q8o+, J8o+, T8o+, 98o, 87o"
    ),
}
"""Opening ranges by players behind (8: under the gun of 9, 1: small blind)."""

HEADS_UP_OPEN = (
    "22+, A2+, K2+, Q2+, J2s+, J4o+, T2s+, T6o+, 92s+, 96o+, 82s+, 86o+, 73s+,"
    " 75o+, 62s+, 65o, 52s+, 42s+, 32s"
)
"""The button (small blind) heads-up raises most hands."""

FOUR_BET = HandRange.parse("QQ+, AKs, AKo")
"""Re-raised after opening (or facing a four-bet): the hands that go on."""
CALL_THREE_BET = HandRange.parse("JJ-77, AQs-ATs, KQs, AQo")
"""Opened, then re-raised: the hands that call with deep stacks."""

THREE_BET_SHARE = 0.25
"""Share of the opener's range the re-raising range covers."""
CALL_SHARE = 0.45
"""Share of the opener's range flat-called in position."""
BIG_BLIND_CALL_SHARE = 0.75
"""Share of the opener's range the big blind defends by calling."""
MIN_THREE_BET_PERCENT = 2.5
MAX_THREE_BET_PERCENT = 12.0


def players_behind(position: Position, dealt_in: tuple[Position, ...]) -> int:
    """The players dealt in who act after ``position`` pre-flop."""
    if len(dealt_in) == 2:
        return 1 if position == Position.BTN else 0

    order = PREFLOP_ORDER.index(position)

    return sum(1 for other in dealt_in if PREFLOP_ORDER.index(other) > order)


@cache
def open_range(behind: int, heads_up: bool = False) -> HandRange:
    if heads_up:
        return HandRange.parse(HEADS_UP_OPEN)

    return HandRange.parse(OPEN_RANGES[min(max(behind, 1), max(OPEN_RANGES))])


def open_percent(behind: int, heads_up: bool = False) -> float:
    """The share of hands (percent) opened with that many players behind."""
    return open_range(behind, heads_up).share * 100


def hand_percent(hole_cards: tuple[Card, ...]) -> float:
    """The share of hands stronger than these (``HAND_ORDER``), in percent."""
    return PERCENT_BEFORE[hand_class(hole_cards)]


def three_bet_percent(opener_percent: float) -> float:
    """Re-raising range (percent of hands) against an opener's range."""
    share = opener_percent * THREE_BET_SHARE

    return min(max(share, MIN_THREE_BET_PERCENT), MAX_THREE_BET_PERCENT)


def call_percent(opener_percent: float, big_blind: bool) -> float:
    """Up to which percent of hands a raise is flat-called (re-raises
    included)."""
    share = BIG_BLIND_CALL_SHARE if big_blind else CALL_SHARE

    return three_bet_percent(opener_percent) + opener_percent * share
