# game/helper.py

from __future__ import annotations

import os

from .models.models import Player


def clear_terminal() -> None:
    """Clear the terminal screen."""

    os.system(
        "cls" if os.name == "nt" else "clear",
    )


def wait() -> None:
    """Pause until the user presses Enter."""

    input("\nPress ENTER to continue...")


def get_circular_players(
    players: list[Player],
    start_index: int,
) -> list[Player]:
    """
    Return players in circular order starting at start_index.
    """

    if not players:
        return []

    start_index %= len(players)

    return players[start_index:] + players[:start_index]


def get_next_player(
    players: list[Player],
    player: Player,
) -> Player | None:
    """Return the next player in circular order."""

    if not players:
        return None

    try:
        index = players.index(player)
    except ValueError:
        return None

    next_index = (index + 1) % len(players)

    return players[next_index]
