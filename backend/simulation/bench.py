"""Reproducible single-core benchmark of the simulator.

Every table is seeded and played on one core with the default checks
(chip invariants on, no history), so the numbers can be compared from one
version of the engine to the next.
"""

from dataclasses import dataclass

from .config import SeatSpec, SimulationConfig
from .runner import run_simulation

BENCH_SEED = 20261116


@dataclass(frozen=True)
class BenchTable:
    """One benchmarked table."""

    name: str
    bots: tuple[str, ...]


BENCH_TABLES: tuple[BenchTable, ...] = (
    BenchTable("6 BasicBots", ("basic",) * 6),
    BenchTable("6-style table", ("nit", "tag", "lag", "station", "maniac", "basic")),
    BenchTable("Heads-up TAG vs LAG", ("tag", "lag")),
)


@dataclass(frozen=True)
class BenchResult:
    table: BenchTable
    hands: int
    seconds: float

    @property
    def hands_per_second(self) -> float:
        return self.hands / self.seconds if self.seconds > 0 else 0.0


def bench_config(table: BenchTable, hands: int) -> SimulationConfig:
    return SimulationConfig(
        seats=tuple(SeatSpec(bot) for bot in table.bots),
        hands=hands,
        seed=BENCH_SEED,
        workers=1,
    )


def run_bench(
    hands: int, tables: tuple[BenchTable, ...] = BENCH_TABLES
) -> list[BenchResult]:
    """Play ``hands`` hands of every table on one core."""
    results = []

    for table in tables:
        result = run_simulation(bench_config(table, hands))
        results.append(
            BenchResult(
                table=table, hands=result.totals.hands, seconds=result.duration_seconds
            )
        )

    return results
