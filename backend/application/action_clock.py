"""The human player's action clock and time bank.

As on online poker sites, each decision has a fixed time to act. When it runs
out, a time bank (a reserve shared by the whole session or tournament) starts
automatically. When both are used up, the hand is dead: the player checks if
checking is free, and folds otherwise. Unused time to act is not saved, and
the time bank is topped up slowly as hands are played.

Time is measured here, in the application layer, from an injectable time
source so the clock can be tested without waiting; the engine never knows
about time. Bots have no clock, and simulations never use one.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.constants import ActionType
from backend.poker_engine.models import ActionEvent, Hand

TimeSource = Callable[[], float]


@dataclass(frozen=True)
class ClockPreset:
    """How much time the human has, in seconds."""

    name: str
    time_to_act: float
    time_bank: float
    """The time bank at the start of the session or tournament."""
    top_up: float
    top_up_every_hands: int
    max_time_bank: float

    def describe(self) -> str:
        return f"{self.name} — {self.time_to_act:g} s + {self.time_bank:g} s bank"


OFF = "Off"
"""No clock: unlimited time to act."""

CLOCK_PRESETS: tuple[ClockPreset, ...] = (
    ClockPreset(
        "Relaxed", 30, 120, top_up=10, top_up_every_hands=25, max_time_bank=120
    ),
    ClockPreset(
        "Standard", 20, 60, top_up=10, top_up_every_hands=25, max_time_bank=120
    ),
    ClockPreset("Fast", 15, 30, top_up=5, top_up_every_hands=25, max_time_bank=60),
    ClockPreset("Hyper", 10, 20, top_up=5, top_up_every_hands=25, max_time_bank=40),
)
CLOCK_CHOICES: tuple[str, ...] = (OFF, *(preset.name for preset in CLOCK_PRESETS))

CASH_CLOCK = "Standard"
TOURNAMENT_CLOCK = "Standard"
TURBO_TOURNAMENT_CLOCK = "Fast"
SPIN_CLOCK = "Fast"

WARNING_SECONDS = 5
"""The clock turns to a warning colour for the last seconds to act."""


def clock_preset(name: str) -> ClockPreset | None:
    """Return the preset called ``name``, or None for "Off"."""
    if name == OFF:
        return None

    for preset in CLOCK_PRESETS:
        if preset.name == name:
            return preset

    raise ValueError(f"Unknown clock preset: {name!r}.")


def tournament_clock(structure_name: str) -> str:
    """The default clock of a tournament: faster for a Turbo structure."""
    if structure_name.lower() == "turbo":
        return TURBO_TOURNAMENT_CLOCK

    return TOURNAMENT_CLOCK


class ActionClock:
    """Time to act on each decision, then a time bank shared by every hand."""

    def __init__(self, preset: ClockPreset, time_source: TimeSource = time.monotonic):
        self.preset = preset
        self._now = time_source
        self.time_bank = preset.time_bank
        """Seconds left in the time bank, outside the current turn."""
        self.hands_played = 0
        self._turn_start: float | None = None
        self._paused_at: float | None = None
        self._paused_for = 0.0

    # --- The current turn -------------------------------------------------------

    @property
    def is_turn_running(self) -> bool:
        return self._turn_start is not None

    @property
    def is_paused(self) -> bool:
        return self._paused_at is not None

    def start_turn(self) -> None:
        """Start the clock: the human has a decision to make."""
        if self.is_turn_running:
            raise RuntimeError("The clock is already running.")

        self._turn_start = self._now()
        self._paused_at = None
        self._paused_for = 0.0

    def end_turn(self) -> None:
        """Stop the clock once the human acted; the time bank used is gone."""
        if not self.is_turn_running:
            return

        self.time_bank = self.time_bank_left()
        self._turn_start = None
        self._paused_at = None
        self._paused_for = 0.0

    def pause(self) -> None:
        """Freeze the turn's clock (and time bank) where it is."""
        if self.is_turn_running and not self.is_paused:
            self._paused_at = self._now()

    def resume(self) -> None:
        """Restart the clock exactly where it was paused."""
        if self._paused_at is not None:
            self._paused_for += self._now() - self._paused_at
            self._paused_at = None

    def elapsed(self) -> float:
        """Seconds of the current turn, pauses excluded."""
        if self._turn_start is None:
            return 0.0

        now = self._paused_at if self._paused_at is not None else self._now()

        return now - self._turn_start - self._paused_for

    def time_to_act_left(self) -> float:
        return max(0.0, self.preset.time_to_act - self.elapsed())

    def time_bank_left(self) -> float:
        """The time bank left, counting what the current turn already used."""
        used = max(0.0, self.elapsed() - self.preset.time_to_act)

        return max(0.0, self.time_bank - used)

    @property
    def is_in_time_bank(self) -> bool:
        return self.is_turn_running and self.elapsed() > self.preset.time_to_act

    @property
    def is_expired(self) -> bool:
        """True once the time to act and the time bank are both used up."""
        limit = self.preset.time_to_act + self.time_bank

        return self.is_turn_running and self.elapsed() >= limit

    # --- Between hands ----------------------------------------------------------

    def on_hand_finished(self) -> None:
        """Count a hand played; every few hands, top up the time bank."""
        self.hands_played += 1

        if self.hands_played % self.preset.top_up_every_hands == 0:
            self.time_bank = min(
                self.preset.max_time_bank, self.time_bank + self.preset.top_up
            )


def timeout_action(legal_actions: tuple[LegalAction, ...]) -> Action:
    """The action of a player whose time ran out: check if free, else fold."""
    if any(action.type == ActionType.CHECK for action in legal_actions):
        return Action(type=ActionType.CHECK)

    return Action(type=ActionType.FOLD)


def record_timeout(hand: Hand, event: ActionEvent) -> None:
    """Mark an action of the hand history as decided by the clock."""
    hand.timed_out_actions.append(event.sequence)
