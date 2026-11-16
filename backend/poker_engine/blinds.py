"""Blind levels, antes and blind structures.

A level is the forced bets of a hand: small blind, big blind and ante.

**Antes are dead money.** They go into the pot, but they are not part of a
player's bet on the street: they never count toward the amount to call or
toward the size of a raise.

Two ante types:

- **Classic**: every player dealt in posts ``ante``. Each ante counts in the
  player's total contribution, so a player all-in for a short ante only wins
  what every other player matched of it (main and side pots).
- **Big-blind ante**: the big blind alone posts ``ante`` for the whole table.
  It goes into the main pot (``Hand.dead_money``), which every player dealt
  in can win, even when the big blind is all-in for less or folds.

Posting order when a stack is short:

- Classic: **ante first, then the blind**. A player who cannot cover the ante
  posts what they have and is all-in; they are still dealt in.
- Big-blind ante: **blind first, then the ante** (TDA rule), so a short big
  blind completes as much of the big blind as possible and the ante gets what
  is left.

A ``BlindStructure`` lists the levels of a tournament. It never measures time
itself: the caller passes the number of hands played, or the elapsed time the
application measured. After the last level, play stays on the last level.
"""

from dataclasses import dataclass
from enum import StrEnum


class AnteType(StrEnum):
    CLASSIC = "classic"
    BIG_BLIND = "big_blind"


@dataclass(frozen=True)
class BlindLevel:
    """The forced bets of one level."""

    small_blind: int
    big_blind: int
    ante: int = 0
    ante_type: AnteType = AnteType.CLASSIC

    def __post_init__(self) -> None:
        if self.small_blind <= 0:
            raise ValueError("Small blind must be positive.")

        if self.big_blind <= self.small_blind:
            raise ValueError("Big blind must be greater than small blind.")

        if self.ante < 0:
            raise ValueError("Ante cannot be negative.")

    def dead_money(self, players_dealt_in: int) -> int:
        """Total antes put in the pot when every player can cover them."""
        if self.ante_type == AnteType.BIG_BLIND:
            return self.ante

        return self.ante * players_dealt_in

    def describe(self) -> str:
        """For example "50/100, ante 100 (big blind)"."""
        text = f"{self.small_blind}/{self.big_blind}"

        if self.ante:
            kind = " (big blind)" if self.ante_type == AnteType.BIG_BLIND else ""
            text += f", ante {self.ante}{kind}"

        return text


@dataclass(frozen=True)
class BlindStructure:
    """Ordered blind levels and how fast they go up.

    Levels advance every ``hands_per_level`` hands (simulations and tests,
    always deterministic), or every ``minutes_per_level`` minutes of play when
    the application drives a human game by time.
    """

    name: str
    levels: tuple[BlindLevel, ...]
    hands_per_level: int = 10
    minutes_per_level: float = 5.0

    def __post_init__(self) -> None:
        if not self.levels:
            raise ValueError("A blind structure needs at least one level.")

        if self.hands_per_level <= 0:
            raise ValueError("Hands per level must be positive.")

        if self.minutes_per_level <= 0:
            raise ValueError("Minutes per level must be positive.")

    @property
    def last_index(self) -> int:
        return len(self.levels) - 1

    def level(self, index: int) -> BlindLevel:
        """The level at ``index``, staying on the last one after the end."""
        if index < 0:
            raise ValueError("Level indexes start at 0.")

        return self.levels[min(index, self.last_index)]

    def level_index_for_hand(self, hands_played: int) -> int:
        """Index of the level of the next hand after ``hands_played`` hands.

        Levels change between two hands only: with 10 hands per level, hands
        0 to 9 are played at level 0 and hand 10 at level 1.
        """
        if hands_played < 0:
            raise ValueError("The number of hands played cannot be negative.")

        return min(hands_played // self.hands_per_level, self.last_index)

    def level_index_for_time(self, elapsed_seconds: float) -> int:
        """Index of the level reached after ``elapsed_seconds`` of play."""
        if elapsed_seconds < 0:
            raise ValueError("Elapsed time cannot be negative.")

        index = int(elapsed_seconds // (self.minutes_per_level * 60))

        return min(index, self.last_index)

    def hands_until_next_level(self, hands_played: int) -> int | None:
        """Hands left before the level goes up; None on the last level."""
        if self.level_index_for_hand(hands_played) == self.last_index:
            return None

        return self.hands_per_level - hands_played % self.hands_per_level

    def seconds_until_next_level(self, elapsed_seconds: float) -> float | None:
        """Seconds left before the level goes up; None on the last level."""
        if self.level_index_for_time(elapsed_seconds) == self.last_index:
            return None

        level_seconds = self.minutes_per_level * 60

        return level_seconds - elapsed_seconds % level_seconds
