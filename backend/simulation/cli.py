"""Command-line interface of the simulator.

Examples::

    uv run python -m backend.simulation run --seats tag,maniac,maniac,maniac
    uv run python -m backend.simulation run --seats tag,lag --hands 100000 \\
        --workers 8 --duplicate --seed 42
    uv run python -m backend.simulation matchup --bots nit,tag,lag,station
    uv run python -m backend.simulation sweep --bot tag \\
        --param bluff_probability --values 0,0.1,0.2 --field station,maniac
    uv run python -m backend.simulation engine-lab --samples 200000
    uv run python -m backend.simulation bench --hands 20000 --repeat 3
"""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TextIO

from backend.bots.factory import BOT_TYPES

from .bench import BENCH_SEED, BenchResult, run_bench
from .config import SeatSpec, SimulationConfig, StackPolicy
from .engine_lab import check_seven_card_frequencies
from .matchup import MatchupResult, run_matchups, run_sweep
from .result import SimulationResult
from .runner import run_simulation
from .summary import summarize

EXPORT_DIR = Path(__file__).resolve().parents[1] / "data" / "simulations"


def parse_seats(text: str) -> tuple[SeatSpec, ...]:
    """Parse "tag,maniac:Crazy Max,lag" into seats; a name may follow a colon."""
    seats = []

    for item in text.split(","):
        bot, _, name = item.strip().partition(":")

        try:
            seats.append(SeatSpec(bot=bot.strip(), name=name.strip() or None))
        except ValueError as error:
            raise argparse.ArgumentTypeError(str(error)) from error

    return tuple(seats)


def parse_blinds(text: str) -> tuple[int, int]:
    small, separator, big = text.partition("/")

    if not separator:
        raise argparse.ArgumentTypeError("Blinds are written small/big, e.g. 5/10.")

    return int(small), int(big)


def parse_values(text: str) -> list[float]:
    return [float(value) for value in text.split(",") if value.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.simulation",
        description="Headless No Limit Hold'em simulations between bots.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Play a table of bots and report stats.")
    run.add_argument(
        "--seats", type=parse_seats, required=True, help="Bots, e.g. tag,maniac,lag."
    )
    _add_table_options(run)

    matchup = commands.add_parser("matchup", help="Heads-up matrix between bots.")
    matchup.add_argument("--bots", type=parse_seats, required=True)
    _add_table_options(matchup)

    sweep = commands.add_parser("sweep", help="Vary one parameter of a profile.")
    sweep.add_argument("--bot", required=True, help="Profile of the swept bot.")
    sweep.add_argument("--param", required=True, help="BotProfile parameter.")
    sweep.add_argument("--values", type=parse_values, required=True)
    sweep.add_argument(
        "--field", type=parse_seats, required=True, help="The opponents, e.g. tag,lag."
    )
    _add_table_options(sweep)

    lab = commands.add_parser("engine-lab", help="Validate the engine statistically.")
    lab.add_argument("--samples", type=int, default=200_000, help="7-card hands.")
    lab.add_argument(
        "--seats",
        type=parse_seats,
        default=parse_seats("random,random,random,random,random,random"),
    )
    _add_table_options(lab, default_hands=20_000)

    commands.add_parser("bots", help="List the available bots.")

    bench = commands.add_parser("bench", help="Single-core speed of fixed tables.")
    bench.add_argument("--hands", type=int, default=20_000, help="Hands per table.")
    bench.add_argument(
        "--repeat", type=int, default=3, help="Runs per table; the fastest is kept."
    )

    return parser


def _add_table_options(
    parser: argparse.ArgumentParser, default_hands: int = 10_000
) -> None:
    parser.add_argument("--hands", type=int, default=default_hands)
    parser.add_argument("--sessions", type=int, default=100)
    parser.add_argument("--blinds", type=parse_blinds, default=(5, 10))
    parser.add_argument("--stack", type=int, default=1000, help="Starting stack.")
    parser.add_argument(
        "--policy",
        choices=[policy.value for policy in StackPolicy],
        default=StackPolicy.RESET_EACH_HAND.value,
        help="Stack policy: reset each hand, auto rebuy or elimination.",
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1)
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--max-hands-per-session", type=int, default=5000)
    parser.add_argument("--duplicate", action="store_true")
    parser.add_argument("--history", action="store_true", help="Keep hand histories.")
    parser.add_argument(
        "--no-invariants", action="store_true", help="Skip the chip checks."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Export directory (default: backend/data/simulations/<time>).",
    )
    parser.add_argument("--no-export", action="store_true")


def config_from_args(
    args: argparse.Namespace, seats: tuple[SeatSpec, ...]
) -> SimulationConfig:
    small_blind, big_blind = args.blinds

    return SimulationConfig(
        seats=seats,
        hands=args.hands,
        sessions=args.sessions,
        small_blind=small_blind,
        big_blind=big_blind,
        starting_stack=args.stack,
        stack_policy=StackPolicy(args.policy),
        seed=args.seed,
        workers=args.workers,
        batch_size=args.batch_size,
        max_hands_per_session=args.max_hands_per_session,
        duplicate=args.duplicate,
        record_history=args.history,
        check_invariants=not args.no_invariants,
    )


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return _dispatch(args, out or sys.stdout)
    except ValueError as error:
        parser.error(str(error))


def _dispatch(args: argparse.Namespace, out: TextIO) -> int:
    if args.command == "bots":
        for bot_type in BOT_TYPES.values():
            print(
                f"{bot_type.key:<8} {bot_type.label:<16} {bot_type.description}",
                file=out,
            )
        return 0

    if args.command == "bench":
        print_bench(run_bench(args.hands, args.repeat), out)
        return 0

    if args.command == "run":
        config = config_from_args(args, args.seats)
        result = run_simulation(config, progress=ProgressPrinter(out))
        print_result(result, out)
        _export(args, "run", out, result=result)
        return 0

    if args.command == "matchup":
        config = config_from_args(args, args.bots[:2])
        matchup = run_matchups(
            args.bots, config, progress=ProgressPrinter(out, "matchups")
        )
        print_matrix(matchup, out)
        _export(args, "matchup", out, data=matchup.to_dict())
        return 0

    if args.command == "sweep":
        config = config_from_args(args, (SeatSpec(args.bot), *args.field))
        sweep = run_sweep(
            args.bot,
            args.param,
            args.values,
            args.field,
            config,
            progress=ProgressPrinter(out, "runs"),
        )
        print(f"\n{args.bot} — {args.param}", file=out)

        for point in sweep.points:
            print(
                f"  {point.value:>8g}  "
                + _format_rate(point.win_rate.bb_per_100, point.win_rate.ci95),
                file=out,
            )

        _export(args, "sweep", out, data=sweep.to_dict())
        return 0

    # engine-lab
    report = check_seven_card_frequencies(args.samples, seed=args.seed or 0)
    print(f"\n7-card categories over {report.samples:,} random hands", file=out)
    print(f"{'Category':<18}{'observed':>10}{'expected':>10}{'z':>8}", file=out)

    for check in report.checks:
        print(
            f"{check.category.name:<18}{check.observed_probability:>10.4%}"
            f"{check.expected_probability:>10.4%}{check.z_score:>8.2f}",
            file=out,
        )

    print(
        f"Max |z| = {report.max_abs_z_score:.2f} "
        f"({report.evaluations_per_second:,.0f} evaluations/s)",
        file=out,
    )
    config = config_from_args(args, args.seats)
    result = run_simulation(config, progress=ProgressPrinter(out))
    print_engine_lab(result, out)
    _export(args, "engine-lab", out, result=result)
    return 0


class ProgressPrinter:
    """Prints the progress on a single line."""

    def __init__(self, out: TextIO, unit: str = "") -> None:
        self._out = out
        self._unit = unit

    def __call__(self, done: int, total: int) -> None:
        end = "\n" if done == total else ""
        unit = f" {self._unit}" if self._unit else ""
        print(f"\r  {done:,} / {total:,}{unit}", end=end, file=self._out, flush=True)


def _format_percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def _format_number(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _format_rate(rate: float | None, interval: tuple[float, float] | None) -> str:
    if rate is None:
        return "—"

    if interval is None:
        return f"{rate:+.1f}"

    return f"{rate:+.1f} ±{(interval[1] - interval[0]) / 2:.1f}"


def print_result(result: SimulationResult, out: TextIO) -> None:
    config = result.config
    print(
        f"\n{result.totals.hands:,} hands in {result.duration_seconds:.1f}s "
        f"({result.hands_per_second:,.0f} hands/s) — seed {config.seed}, "
        f"policy {config.stack_policy.value}"
        + (", duplicate" if config.duplicate else ""),
        file=out,
    )

    headers = (
        "Player",
        "Hands",
        "bb/100",
        "Net",
        "VPIP",
        "PFR",
        "3B",
        "AF",
        "WTSD",
        "W$SD",
    )
    rows = [
        (
            stats.name,
            f"{stats.hands:,}",
            _format_rate(
                stats.bb_per_100(config.big_blind),
                stats.confidence_interval_bb_per_100(config.big_blind),
            ),
            f"{stats.net_chips:+,}",
            _format_percent(stats.vpip),
            _format_percent(stats.pfr),
            _format_percent(stats.three_bet),
            _format_number(stats.aggression_factor),
            _format_percent(stats.wtsd),
            _format_percent(stats.wsd),
        )
        for stats in result.ranking()
    ]

    if config.stack_policy == StackPolicy.ELIMINATION:
        headers = (*headers, "Win %", "Avg finish")
        rows = [
            (
                *row,
                _format_percent(stats.win_rate),
                _format_number(stats.average_finish),
            )
            for row, stats in zip(rows, result.ranking(), strict=True)
        ]
    elif config.stack_policy == StackPolicy.AUTO_REBUY:
        headers = (*headers, "Rebuys")
        rows = [
            (*row, str(stats.rebuys))
            for row, stats in zip(rows, result.ranking(), strict=True)
        ]

    print_table(headers, rows, out)

    for sentence in summarize(result):
        print(sentence, file=out)

    if result.totals.capped_sessions:
        print(f"Capped sessions: {result.totals.capped_sessions}", file=out)


def print_bench(results: Sequence[BenchResult], out: TextIO) -> None:
    print(f"\nOne core, seed {BENCH_SEED}, chip checks on, best run", file=out)
    print_table(
        ("Table", "Hands", "Seconds", "Hands/s"),
        [
            (
                result.table.name,
                f"{result.hands:,}",
                f"{result.seconds:.1f}",
                f"{result.hands_per_second:,.0f}",
            )
            for result in results
        ],
        out,
    )


def print_engine_lab(result: SimulationResult, out: TextIO) -> None:
    engine = result.engine
    print(
        f"\nEngine Lab — {engine.hands:,} hands, "
        f"{result.hands_per_second:,.0f} hands/s",
        file=out,
    )
    print(f"  Showdowns: {_format_percent(engine.showdown_frequency)}", file=out)
    print(
        f"  Split pots: {_format_number((engine.split_pot_frequency or 0) * 100)}%",
        file=out,
    )
    print(f"  All-in hands: {_format_percent(engine.all_in_frequency)}", file=out)
    print(f"  Auto run-outs: {_format_percent(engine.runout_frequency)}", file=out)
    side_pots = ", ".join(
        f"{count} side pot(s): {hands:,}"
        for count, hands in sorted(engine.side_pot_counts.items())
    )
    print(f"  Showdowns by side pots: {side_pots or '—'}", file=out)

    for category, frequency in engine.category_frequencies().items():
        print(f"  {category:<18}{_format_number((frequency or 0) * 100)}%", file=out)


def print_matrix(matchup: MatchupResult, out: TextIO) -> None:
    """Print bb/100 of each row bot against each column bot."""
    count = len(matchup.names)
    rows = []

    for row, name in enumerate(matchup.names):
        cells = [matchup.cell(row, column) for column in range(count)]
        rows.append(
            (
                name,
                *(
                    "—" if cell is None else _format_rate(cell.bb_per_100, cell.ci95)
                    for cell in cells
                ),
            )
        )

    print("\nbb/100 of the row bot against the column bot (heads-up)", file=out)
    print_table(("", *matchup.names), rows, out)


def print_table(
    headers: Sequence[str], rows: Sequence[Sequence[str]], out: TextIO
) -> None:
    widths = [
        max(len(str(cell)) for cell in column)
        for column in zip(headers, *rows, strict=True)
    ]

    def line(cells: Sequence[str]) -> str:
        first, *others = cells
        return "  ".join(
            [f"{first:<{widths[0]}}"]
            + [
                f"{cell:>{width}}"
                for cell, width in zip(others, widths[1:], strict=True)
            ]
        )

    print(line(headers), file=out)
    print("  ".join("-" * width for width in widths), file=out)

    for row in rows:
        print(line(row), file=out)


def _export(
    args: argparse.Namespace,
    command: str,
    out: TextIO,
    result: SimulationResult | None = None,
    data: dict[str, object] | None = None,
) -> None:
    if args.no_export:
        return

    directory = args.output or EXPORT_DIR / (
        datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{command}"
    )

    if result is not None:
        json_path = result.save_json(directory / "result.json")
        csv_path = result.save_csv(directory / "players.csv")
        print(f"\nExported {json_path}\n         {csv_path}", file=out)
        return

    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{command}.json"
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\nExported {json_path}", file=out)
