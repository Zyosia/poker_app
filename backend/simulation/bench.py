"""Reproducible single-core benchmark of the simulator.

Every table is seeded and played on one core with the default checks
(chip invariants on, no history), so the numbers can be compared from one
version of the engine to the next. Use ``--repeat`` on a noisy machine.
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
    hands: int,
    repeat: int = 1,
    tables: tuple[BenchTable, ...] = BENCH_TABLES,
) -> list[BenchResult]:
    """Play ``hands`` hands of every table on one core.

    With ``repeat`` above 1, each table is played several times and the
    fastest run is kept: the other runs only measure interference from the
    rest of the machine, like ``timeit`` does.
    """
    if repeat < 1:
        raise ValueError("A benchmark runs at least once.")

    results = []

    for table in tables:
        config = bench_config(table, hands)
        runs = [run_simulation(config) for _ in range(repeat)]
        results.append(
            BenchResult(
                table=table,
                hands=runs[0].totals.hands,
                seconds=min(run.duration_seconds for run in runs),
            )
        )

    return results
