# backend/game/constants.py

from typing import Final, Literal

Card = str
Rank = str
Suit = str

Street = Literal[
    "PREFLOP",
    "FLOP",
    "TURN",
    "RIVER",
]

ActionType = Literal[
    "fold",
    "check",
    "call",
    "raise",
    "all_in",
]

Position = Literal[
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
