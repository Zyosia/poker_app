"""Shared constants and value types of the poker engine."""

from enum import StrEnum
from typing import Final

Card = str
"""A card is a two-character string: rank followed by suit (for example "AS")."""

RANKS: Final[str] = "23456789TJQKA"
SUITS: Final[str] = "CDHS"

MAX_TABLE_SEATS: Final[int] = 9
"""Seats of a full-ring table: the most players the engine deals in (cash
games, tournaments, Bot Arena, and hands imported from other sites)."""


class Street(StrEnum):
    PREFLOP = "PREFLOP"
    FLOP = "FLOP"
    TURN = "TURN"
    RIVER = "RIVER"


class ActionType(StrEnum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    RAISE = "raise"
    ALL_IN = "all_in"


class Position(StrEnum):
    BTN = "BTN"
    SB = "SB"
    BB = "BB"
    UTG = "UTG"
    HJ = "HJ"
    CO = "CO"
    UTG1 = "UTG+1"
    UTG2 = "UTG+2"
    LJ = "LJ"
