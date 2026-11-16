"""Game modes offered by the main menu."""

from dataclasses import dataclass
from enum import StrEnum


class ScreenKey(StrEnum):
    """Screens a mode can open."""

    CASH_SETUP = "cash_setup"
    ARENA_SETUP = "arena_setup"


@dataclass(frozen=True)
class Mode:
    """One card of the main menu."""

    key: str
    name: str
    description: str
    symbol: str
    screen: ScreenKey | None
    """The screen opened by the mode; None for a mode not available yet."""
    note: str | None = None
    """Shown on the card, e.g. when the mode is coming later."""

    @property
    def enabled(self) -> bool:
        return self.screen is not None


MODES: tuple[Mode, ...] = (
    Mode(
        key="cash",
        name="Cash Game",
        description="Sit down against bots and play hand after hand.",
        symbol="♠",
        screen=ScreenKey.CASH_SETUP,
    ),
    Mode(
        key="arena",
        name="Bot Arena",
        description="Pit play styles against each other and compare them.",
        symbol="♦",
        screen=ScreenKey.ARENA_SETUP,
    ),
    Mode(
        key="tournament",
        name="Tournament",
        description="Rising blinds until one player holds every chip.",
        symbol="♣",
        screen=None,
        note="Coming in V1.0",
    ),
    Mode(
        key="spin",
        name="Spin & Go",
        description="Fast three-player tournaments with a random prize.",
        symbol="♥",
        screen=None,
        note="Coming in V1.0",
    ),
    Mode(
        key="tools",
        name="Tools",
        description="Hand replayer and equity calculator.",
        symbol="◈",
        screen=None,
        note="Coming later",
    ),
)
