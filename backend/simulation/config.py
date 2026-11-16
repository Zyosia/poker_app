"""Configuration of a headless bot simulation."""

import hashlib
import math
import random
from dataclasses import dataclass, replace
from enum import StrEnum

from backend.bots.factory import get_bot_type
from backend.poker_engine.constants import MAX_TABLE_SEATS

MIN_TABLE_SEATS = 2

CHART_SAMPLES = 1000
"""Chip graph samples taken over a run, before downsampling for display."""

ESTIMATED_HANDS_PER_SESSION = 200


class StackPolicy(StrEnum):
    """How stacks evolve between the hands of a simulation."""

    RESET_EACH_HAND = "reset"
    """Every player starts every hand with the starting stack."""

    AUTO_REBUY = "rebuy"
    """A busted player is topped back up to the starting stack.

    Stacks are carried from hand to hand inside a batch only: every batch
    starts from fresh starting stacks.
    """

    ELIMINATION = "elimination"
    """Sessions are played until one player has every chip."""


@dataclass(frozen=True)
class SeatSpec:
    """A bot seated at the simulated table."""

    bot: str
    name: str | None = None
    overrides: tuple[tuple[str, float], ...] = ()
    """Profile parameters replaced for this seat, e.g. (("bluff_probability", 0.2),)."""

    def __post_init__(self) -> None:
        get_bot_type(self.bot).build_profile(self.overrides)

        if self.name is not None and not self.name.strip():
            raise ValueError("A seat name cannot be blank.")


@dataclass(frozen=True)
class SimulationConfig:
    """Everything that determines the outcome of a simulation.

    The budget is ``hands`` for the reset and rebuy policies, and ``sessions``
    (complete sessions) for the elimination policy. The budget is split into
    batches of ``batch_size`` hands or ``sessions_per_batch`` sessions; each
    batch draws its randomness from ``(seed, batch index)``, so the results do
    not depend on the number of ``workers``.
    """

    seats: tuple[SeatSpec, ...]
    hands: int = 10_000
    sessions: int = 100
    small_blind: int = 5
    big_blind: int = 10
    starting_stack: int = 1000
    stack_policy: StackPolicy = StackPolicy.RESET_EACH_HAND
    seed: int | None = None
    workers: int = 1
    batch_size: int = 1000
    sessions_per_batch: int = 10
    max_hands_per_session: int = 5000
    duplicate: bool = False
    record_history: bool = False
    check_invariants: bool = True

    def __post_init__(self) -> None:
        if not MIN_TABLE_SEATS <= len(self.seats) <= MAX_TABLE_SEATS:
            raise ValueError(
                f"A simulation needs {MIN_TABLE_SEATS} to {MAX_TABLE_SEATS} seats."
            )

        names = self.seat_names

        if len(set(names)) != len(names):
            raise ValueError("Seat names must be unique.")

        for field_name in (
            "hands",
            "sessions",
            "small_blind",
            "starting_stack",
            "workers",
            "batch_size",
            "sessions_per_batch",
            "max_hands_per_session",
        ):
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name} must be positive.")

        if self.big_blind <= self.small_blind:
            raise ValueError("The big blind must be greater than the small blind.")

        if self.duplicate and self.stack_policy != StackPolicy.RESET_EACH_HAND:
            raise ValueError(
                "Duplicate mode requires the reset stack policy: with rebuys or "
                "eliminations the stacks diverge between rotations of a deal."
            )

    @property
    def seat_names(self) -> tuple[str, ...]:
        return seat_names(self.seats)

    @property
    def deals(self) -> int:
        """Number of distinct card deals; each is played once per seat in duplicate."""
        if self.duplicate:
            return math.ceil(self.hands / len(self.seats))

        return self.hands

    @property
    def planned_hands(self) -> int | None:
        """Hands that will be played, or None when sessions decide (elimination).

        In duplicate mode every deal is played once per seat rotation, so the
        budget is rounded up to a whole number of deals.
        """
        if self.stack_policy == StackPolicy.ELIMINATION:
            return None

        if self.duplicate:
            return self.deals * len(self.seats)

        return self.hands

    @property
    def chart_stride(self) -> int:
        """Number of hands between two samples of the chip graph."""
        hands = self.planned_hands

        if hands is None:
            hands = self.sessions * ESTIMATED_HANDS_PER_SESSION

        return max(1, hands // CHART_SAMPLES)

    def with_seed(self) -> "SimulationConfig":
        """Return this configuration with a seed, drawing one if none is set."""
        if self.seed is not None:
            return self

        return replace(self, seed=random.SystemRandom().randrange(2**63))


def seat_names(seats: tuple[SeatSpec, ...]) -> tuple[str, ...]:
    """Display name of every seat.

    Custom names are kept as given; default names are the bot label,
    numbered when it appears several times.
    """
    custom_names = {seat.name for seat in seats if seat.name}
    names: list[str] = []

    for seat in seats:
        if seat.name:
            names.append(seat.name)
            continue

        base = get_bot_type(seat.bot).label
        name = base
        number = 2

        while name in names or name in custom_names:
            name = f"{base} {number}"
            number += 1

        names.append(name)

    return tuple(names)


def derive_seed(seed: int, *parts: int | str) -> int:
    """Derive a stable 64-bit seed from a base seed and labels.

    Unlike ``hash()``, the result is the same in every process and run.
    """
    data = ":".join(str(part) for part in (seed, *parts)).encode()

    return int.from_bytes(hashlib.blake2b(data, digest_size=8).digest(), "big")
