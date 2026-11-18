"""Buy-in, rebuy and top-up rules of a cash game (V3.0).

As in online cash games, a seat is bought for **40 to 100 big blinds**:

- the starting stack and every **rebuy** (after busting) are chosen between
  the minimum and the maximum buy-in;
- a **top-up**, between two hands, brings a stack back to the maximum (never
  above it);
- with **bots rebuying**, a busted bot buys the maximum again and a bot that
  falls below the minimum tops up to the maximum, so the table stays full;
- with **auto top-up**, your stack goes back to the maximum before every hand
  (as long as the bankroll pays).

The chips always come from the session (``GameSession.rebuy_player`` and
``add_chips``); the bankroll payments are made by the interface, which knows
the account.
"""

from dataclasses import dataclass

MIN_BUY_IN_BIG_BLINDS = 40
MAX_BUY_IN_BIG_BLINDS = 100


@dataclass(frozen=True)
class BuyInRange:
    """The smallest and largest stack a seat can be bought for, in chips."""

    minimum: int
    maximum: int

    @classmethod
    def for_big_blind(cls, big_blind: int) -> "BuyInRange":
        return cls(MIN_BUY_IN_BIG_BLINDS * big_blind, MAX_BUY_IN_BIG_BLINDS * big_blind)

    def clamp(self, amount: int) -> int:
        return min(max(amount, self.minimum), self.maximum)

    def top_up(self, stack: int) -> int:
        """Chips that bring ``stack`` back to the maximum (0 if already there)."""
        return max(0, self.maximum - stack)


@dataclass(frozen=True)
class Refill:
    """Chips a bot received between two hands."""

    player: str
    amount: int
    rebuy: bool
    """True for a rebuy after busting, False for a top-up."""
