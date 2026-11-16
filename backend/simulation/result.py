"""Results of a simulation and their export to JSON and CSV."""

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import SimulationConfig, StackPolicy
from .stats import (
    STREETS,
    ChartPoint,
    EngineLabStats,
    PlayerStats,
    downsample_chart,
    shift_chart,
)

MAX_CHART_POINTS = 300

CSV_COLUMNS: tuple[str, ...] = (
    "name",
    "bot",
    "hands",
    "net_chips",
    "bb_per_100",
    "ci95_low",
    "ci95_high",
    "sd_per_100",
    "vpip",
    "pfr",
    "three_bet",
    "aggression_factor",
    "aggression_frequency",
    "wtsd",
    "wsd",
    "cbet",
    "fold_to_cbet",
    "rebuys",
    "sessions_won",
    "win_rate",
    "average_finish",
)


@dataclass
class SimulationTotals:
    """Mergeable totals over a set of hands or sessions."""

    players: dict[str, PlayerStats]
    engine: EngineLabStats = field(default_factory=EngineLabStats)
    chart: list[ChartPoint] = field(default_factory=list)
    """Cumulative net chips per seat, sampled along the hands."""
    hands: int = 0
    sessions: int = 0
    capped_sessions: int = 0
    """Elimination sessions stopped by ``max_hands_per_session``."""
    histories: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def empty(cls, config: SimulationConfig) -> "SimulationTotals":
        return cls(
            players={
                name: PlayerStats(name=name, bot=seat.bot)
                for name, seat in zip(config.seat_names, config.seats, strict=True)
            }
        )

    def merge(self, other: "SimulationTotals") -> None:
        """Append the totals of the hands played after these ones.

        Merging in the order the hands were played keeps the chart and the
        histories chronological.
        """
        if list(self.players) != list(other.players):
            raise ValueError("Cannot merge totals of different tables.")

        net_chips = [stats.net_chips for stats in self.players.values()]
        self.chart.extend(shift_chart(other.chart, self.hands, net_chips))

        for name, stats in other.players.items():
            self.players[name].merge(stats)

        self.engine.merge(other.engine)
        self.hands += other.hands
        self.sessions += other.sessions
        self.capped_sessions += other.capped_sessions
        self.histories.extend(other.histories)


@dataclass
class SimulationResult:
    """Outcome of a complete simulation, with the configuration that produced it.

    ``config.seed`` is always set, so the run can be reproduced exactly.
    """

    config: SimulationConfig
    totals: SimulationTotals
    batch_count: int
    duration_seconds: float

    @property
    def players(self) -> dict[str, PlayerStats]:
        return self.totals.players

    @property
    def engine(self) -> EngineLabStats:
        return self.totals.engine

    @property
    def hands_per_second(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0

        return self.totals.hands / self.duration_seconds

    @property
    def chart(self) -> list[ChartPoint]:
        """The chip graph, starting at zero, with at most a few hundred points."""
        start: ChartPoint = (0, tuple(0 for _ in self.players))

        return downsample_chart([start, *self.totals.chart], MAX_CHART_POINTS)

    def ranking(self) -> list[PlayerStats]:
        """Players from the best result to the worst."""
        if self.config.stack_policy == StackPolicy.ELIMINATION:
            return sorted(
                self.players.values(),
                key=lambda stats: (
                    -(stats.win_rate or 0.0),
                    stats.average_finish or float("inf"),
                ),
            )

        return sorted(self.players.values(), key=lambda s: s.net_chips, reverse=True)

    # --- Export --------------------------------------------------------------

    def player_row(self, stats: PlayerStats) -> dict[str, Any]:
        """The CSV row of one player."""
        big_blind = self.config.big_blind
        interval = stats.confidence_interval_bb_per_100(big_blind)

        return {
            "name": stats.name,
            "bot": stats.bot,
            "hands": stats.hands,
            "net_chips": stats.net_chips,
            "bb_per_100": stats.bb_per_100(big_blind),
            "ci95_low": interval[0] if interval else None,
            "ci95_high": interval[1] if interval else None,
            "sd_per_100": stats.standard_deviation_per_100(big_blind),
            "vpip": stats.vpip,
            "pfr": stats.pfr,
            "three_bet": stats.three_bet,
            "aggression_factor": stats.aggression_factor,
            "aggression_frequency": stats.aggression_frequency,
            "wtsd": stats.wtsd,
            "wsd": stats.wsd,
            "cbet": stats.cbet,
            "fold_to_cbet": stats.fold_to_cbet,
            "rebuys": stats.rebuys,
            "sessions_won": stats.finishes[0] if stats.finishes else None,
            "win_rate": stats.win_rate,
            "average_finish": stats.average_finish,
        }

    def to_dict(self) -> dict[str, Any]:
        """Every result of the simulation, as JSON-compatible data."""
        engine = self.engine

        return {
            "config": asdict(self.config),
            "seed": self.config.seed,
            "batch_size": self.config.batch_size,
            "batch_count": self.batch_count,
            "duplicate": self.config.duplicate,
            "deals": self.config.deals if self.config.duplicate else None,
            "hands": self.totals.hands,
            "sessions": self.totals.sessions,
            "capped_sessions": self.totals.capped_sessions,
            "duration_seconds": self.duration_seconds,
            "hands_per_second": self.hands_per_second,
            "players": [
                {
                    **self.player_row(stats),
                    "finishes": stats.finishes,
                    "action_frequencies": {
                        street: stats.action_frequencies(street) for street in STREETS
                    },
                    "action_counts": stats.actions,
                    "positions": {
                        position: asdict(result)
                        for position, result in stats.positions.items()
                    },
                }
                for stats in self.players.values()
            ],
            "engine_lab": {
                **asdict(engine),
                "showdown_frequency": engine.showdown_frequency,
                "split_pot_frequency": engine.split_pot_frequency,
                "all_in_frequency": engine.all_in_frequency,
                "runout_frequency": engine.runout_frequency,
                "category_frequencies": engine.category_frequencies(),
            },
            "chart": {
                "players": list(self.players),
                "points": [[hands, list(values)] for hands, values in self.chart],
            },
            "histories": self.totals.histories,
        }

    def save_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

        return path

    def save_csv(self, path: Path) -> Path:
        """Write one row per player."""
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
            writer.writeheader()

            for stats in self.ranking():
                writer.writerow(self.player_row(stats))

        return path
