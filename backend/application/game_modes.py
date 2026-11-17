"""The kinds of game a user plays: recorded by the bankroll and the session files."""

from enum import StrEnum


class GameMode(StrEnum):
    CASH = "cash"
    TOURNAMENT = "tournament"
    SPIN = "spin"


MODE_LABELS = {
    GameMode.CASH: "Cash game",
    GameMode.TOURNAMENT: "Tournament",
    GameMode.SPIN: "Spin & Go",
}
