"""Game modes offered by the main menu."""

from dataclasses import dataclass
from enum import StrEnum


class ScreenKey(StrEnum):
    """Screens a mode can open."""

    CASH_SETUP = "cash_setup"
    ARENA_SETUP = "arena_setup"
    TOURNAMENT_SETUP = "tournament_setup"
    SPIN_SETUP = "spin_setup"
    TOOLS = "tools"
    REPLAYER = "replayer"
    EQUITY = "equity"
    MY_STATS = "my_stats"
    SESSIONS = "sessions"


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
        screen=ScreenKey.TOURNAMENT_SETUP,
    ),
    Mode(
        key="spin",
        name="Spin & Go",
        description="Fast three-player tournaments with a random prize.",
        symbol="♥",
        screen=ScreenKey.SPIN_SETUP,
    ),
    Mode(
        key="tools",
        name="Tools",
        description="Hand replayer, equity calculator, your stats and sessions.",
        symbol="◈",
        screen=ScreenKey.TOOLS,
    ),
)

TOOLS: tuple[Mode, ...] = (
    Mode(
        key="replayer",
        name="Hand Replayer",
        description="Your last hand, step by step; any saved hand from Sessions.",
        symbol="▶",
        screen=ScreenKey.REPLAYER,
    ),
    Mode(
        key="equity",
        name="Equity Calculator",
        description="Win chances of any hands, or random ones, on any board.",
        symbol="%",
        screen=ScreenKey.EQUITY,
    ),
    Mode(
        key="my_stats",
        name="My Stats",
        description="Your VPIP, PFR, aggression and results across sessions.",
        symbol="≡",
        screen=ScreenKey.MY_STATS,
    ),
    Mode(
        key="sessions",
        name="Sessions",
        description="Your saved games: results, chip graph and every hand.",
        symbol="▤",
        screen=ScreenKey.SESSIONS,
    ),
)
