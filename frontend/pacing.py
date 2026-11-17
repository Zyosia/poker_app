"""How fast the table plays: bot actions, streets and the pause between hands.

The default, Normal, is close to online poker clients: a bot acts about a
second after the previous action, and the result of a hand stays on screen
about three seconds before the next one is dealt. The board of an all-in
run-out is dealt a little slower than an action (see ``frontend.runout``).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TableSpeed:
    name: str
    action_delay_ms: int
    """Before each bot action or street."""
    hand_pause_ms: int
    """The result shown before the next hand starts on its own."""


TABLE_SPEEDS: tuple[TableSpeed, ...] = (
    TableSpeed("Slow", action_delay_ms=1500, hand_pause_ms=5000),
    TableSpeed("Normal", action_delay_ms=900, hand_pause_ms=3000),
    TableSpeed("Fast", action_delay_ms=450, hand_pause_ms=1500),
    TableSpeed("Turbo", action_delay_ms=150, hand_pause_ms=600),
)
DEFAULT_TABLE_SPEED = "Normal"


def table_speed(name: str) -> TableSpeed:
    """The speed called ``name``; the default one for an unknown name."""
    for speed in TABLE_SPEEDS:
        if speed.name == name:
            return speed

    return table_speed(DEFAULT_TABLE_SPEED)
