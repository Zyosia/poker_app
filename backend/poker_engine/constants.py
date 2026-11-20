"""Shared constants and value types of the poker engine."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

Card = str
"""A card is a two-character string: rank followed by suit (for example "AS")."""

RANKS: Final[str] = "23456789TJQKA"
SUITS: Final[str] = "CDHS"

MAX_TABLE_SEATS: Final[int] = 9
"""Seats of a full-ring table: the most players the engine deals in (cash
games, tournaments, Bot Arena, and hands imported from other sites)."""


class BettingStructure(StrEnum):
    """How much a player may bet or raise (V3.1.1)."""

    NO_LIMIT = "no_limit"
    """Any amount from the minimum raise up to the whole stack."""
    POT_LIMIT = "pot_limit"
    """Up to the size of the pot after calling."""
    FIXED_LIMIT = "fixed_limit"
    """One fixed size: the big blind pre-flop and on the flop (the small bet),
    twice the big blind on the turn and the river (the big bet)."""


FIXED_LIMIT_BET_CAP: Final[int] = 4
"""Fixed Limit: a bet and three raises per betting round, unless the table
sets another cap."""
MIN_BET_CAP: Final[int] = 2
"""A cap of one bet would forbid any raise: a bet and a raise at least."""


@dataclass(frozen=True)
class BettingRules:
    """The betting structure of a table, and its cap.

    ``cap`` is the most bets and raises in one betting round, the big blind
    counting as the pre-flop bet (a straddle as the first raise). None: no
    cap in No Limit and Pot Limit, and the usual four bets in Fixed Limit.
    The cap applies heads-up too, as in online rooms.
    """

    structure: BettingStructure = BettingStructure.NO_LIMIT
    cap: int | None = None

    def __post_init__(self) -> None:
        if self.cap is not None and self.cap < MIN_BET_CAP:
            raise ValueError(f"A betting cap allows at least {MIN_BET_CAP} bets.")

    @property
    def table_cap(self) -> int | None:
        """The cap the tables play with (``cap`` or the Fixed Limit one)."""
        if self.cap is None and self.structure == BettingStructure.FIXED_LIMIT:
            return FIXED_LIMIT_BET_CAP

        return self.cap


NO_LIMIT: Final[BettingRules] = BettingRules()


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
