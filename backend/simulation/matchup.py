"""Bot development tools: heads-up matchup matrix and parameter sweep."""

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from itertools import combinations
from typing import Any

from backend.bots.factory import get_bot_type

from .config import SeatSpec, SimulationConfig, derive_seed
from .result import SimulationResult
from .runner import run_simulation
from .stats import PlayerStats

RunProgress = Callable[[int, int], None]
"""Called with (runs finished, total runs)."""


@dataclass(frozen=True)
class WinRate:
    """A bb/100 win rate and its 95% confidence interval."""

    bb_per_100: float | None
    ci95: tuple[float, float] | None
    hands: int

    @classmethod
    def of(cls, stats: PlayerStats, big_blind: int) -> "WinRate":
        return cls(
            bb_per_100=stats.bb_per_100(big_blind),
            ci95=stats.confidence_interval_bb_per_100(big_blind),
            hands=stats.hands,
        )

    def to_dict(self) -> dict[str, Any]:
        return {"bb_per_100": self.bb_per_100, "ci95": self.ci95, "hands": self.hands}


@dataclass(frozen=True)
class MatchupResult:
    """``cells[(i, j)]`` is the win rate of bot ``i`` playing heads-up against ``j``."""

    names: tuple[str, ...]
    cells: dict[tuple[int, int], WinRate]
    config: SimulationConfig

    def cell(self, row: int, column: int) -> WinRate | None:
        return self.cells.get((row, column))

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.config.seed,
            "hands_per_matchup": self.config.hands,
            "duplicate": self.config.duplicate,
            "bots": list(self.names),
            "matrix": [
                [
                    cell.to_dict() if (cell := self.cell(row, column)) else None
                    for column in range(len(self.names))
                ]
                for row in range(len(self.names))
            ],
        }


def run_matchups(
    bots: Sequence[SeatSpec],
    base_config: SimulationConfig,
    progress: RunProgress | None = None,
    cancel: threading.Event | None = None,
) -> MatchupResult:
    """Play every pair of bots heads-up and collect both win rates.

    ``base_config`` gives the hands, blinds, stacks, seed and workers of
    every matchup; its seats are replaced by each pair.
    """
    if len(bots) < 2:
        raise ValueError("A matchup needs at least two bots.")

    base_config = base_config.with_seed()
    assert base_config.seed is not None
    names = _unique_names(bots)
    pairs = list(combinations(range(len(bots)), 2))
    cells: dict[tuple[int, int], WinRate] = {}

    for done, (first, second) in enumerate(pairs, start=1):
        seats = (
            replace(bots[first], name=names[first]),
            replace(bots[second], name=names[second]),
        )
        config = replace(
            base_config,
            seats=seats,
            seed=derive_seed(base_config.seed, "matchup", first, second),
        )
        result = run_simulation(config, cancel=cancel)
        big_blind = config.big_blind
        cells[first, second] = WinRate.of(result.players[names[first]], big_blind)
        cells[second, first] = WinRate.of(result.players[names[second]], big_blind)

        if progress is not None:
            progress(done, len(pairs))

    return MatchupResult(names=names, cells=cells, config=base_config)


@dataclass(frozen=True)
class SweepPoint:
    value: float
    win_rate: WinRate
    result: SimulationResult


@dataclass(frozen=True)
class SweepResult:
    bot: str
    parameter: str
    points: tuple[SweepPoint, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "bot": self.bot,
            "parameter": self.parameter,
            "points": [
                {"value": point.value, **point.win_rate.to_dict()}
                for point in self.points
            ],
        }


def run_sweep(
    bot: str,
    parameter: str,
    values: Sequence[float],
    field: Sequence[SeatSpec],
    base_config: SimulationConfig,
    progress: RunProgress | None = None,
    cancel: threading.Event | None = None,
) -> SweepResult:
    """Run one profile against a fixed field, once per value of a parameter.

    The swept bot sits in the first seat. Every run uses the same seed, so
    the values are compared on the same cards.
    """
    if not values:
        raise ValueError("A sweep needs at least one value.")

    base_config = base_config.with_seed()
    points: list[SweepPoint] = []
    name = "Swept"

    for done, value in enumerate(values, start=1):
        swept = SeatSpec(bot=bot, name=name, overrides=((parameter, value),))
        config = replace(base_config, seats=(swept, *field))
        result = run_simulation(config, cancel=cancel)
        points.append(
            SweepPoint(
                value=value,
                win_rate=WinRate.of(result.players[name], config.big_blind),
                result=result,
            )
        )

        if progress is not None:
            progress(done, len(values))

    return SweepResult(bot=bot, parameter=parameter, points=tuple(points))


def _unique_names(bots: Sequence[SeatSpec]) -> tuple[str, ...]:
    """Name every bot of a matchup list, numbering repeated bots."""
    names: list[str] = []

    for bot in bots:
        base = bot.name or get_bot_type(bot.bot).label
        name = base
        number = 2

        while name in names:
            name = f"{base} {number}"
            number += 1

        names.append(name)

    return tuple(names)
