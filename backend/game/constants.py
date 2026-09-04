# game/constants.py

from typing import Final, Literal, TypeAlias

Card: TypeAlias = str
Rank: TypeAlias = str
Suit: TypeAlias = str

Street: TypeAlias = Literal[
    "PREFLOP",
    "FLOP",
    "TURN",
    "RIVER",
]

ActionType: TypeAlias = Literal[
    "fold",
    "check",
    "call",
    "raise",
    "all_in",
]

Position: TypeAlias = Literal[
    "BTN",
    "SB",
    "BB",
    "UTG",
    "HJ",
    "CO",
]


RANKS: Final[str] = "23456789TJQKA"
SUITS: Final[str] = "CDHS"

POSITIONS: Final[tuple[Position, ...]] = (
    "BTN",
    "SB",
    "BB",
    "UTG",
    "HJ",
    "CO",
)

STREETS: Final[tuple[Street, ...]] = (
    "PREFLOP",
    "FLOP",
    "TURN",
    "RIVER",
)

ACTIONS: Final[tuple[ActionType, ...]] = (
    "fold",
    "check",
    "call",
    "raise",
    "all_in",
)
