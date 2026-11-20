"""Bot Arena runs of complete tournaments and Spin & Go games.

The budget is a number of tournaments. Batches hold complete tournaments,
each seeded from ``(seed, tournament index)``, so the results do not depend
on the number of workers (like the elimination sessions of cash runs).

**Seat fairness**: in tournament ``t`` the bot listed at index ``i`` sits in
seat ``(i + t) % n``, so over ``n`` consecutive tournaments every bot sits in
every seat once. The first button is drawn from the tournament's seed.
"""

import csv
import json
import math
import random
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from fractions import Fraction
from functools import partial
from pathlib import Path
from typing import Any

from backend.application.payouts import (
    FAIR_MULTIPLIERS,
    REALISTIC_MULTIPLIERS,
    TOP_THREE,
    TOP_TWO,
    WINNER_TAKES_ALL,
    MultiplierTable,
    PayoutStructure,
)
from backend.application.structures import (
    DEEP,
    REGULAR,
    SPIN_HYPER_TURBO,
    SPIN_PLAYERS,
    SPIN_STARTING_STACK,
    TOURNAMENT_STARTING_STACK,
    TURBO,
)
from backend.application.tournament import (
    RebuyRules,
    SpinConfig,
    Tournament,
    TournamentConfig,
    TournamentResult,
    create_spin,
)
from backend.bots.factory import create_bot
from backend.poker_engine.blinds import BlindStructure
from backend.poker_engine.constants import MAX_TABLE_SEATS, NO_LIMIT, BettingRules
from backend.poker_engine.models import Hand

from .config import (
    MIN_TABLE_SEATS,
    SeatSpec,
    derive_seed,
    exported_config,
    seat_names,
)
from .invariants import InvariantError, find_chip_violations
from .runner import Batch, ProgressCallback, execute_batches
from .stats import CONFIDENCE_Z
from .tournament_stats import TournamentPlayerStats, TournamentTotals


class RunType(StrEnum):
    TOURNAMENT = "tournament"
    SPIN = "spin"


STRUCTURES: dict[str, BlindStructure] = {
    "turbo": TURBO,
    "regular": REGULAR,
    "deep": DEEP,
    "hyper": SPIN_HYPER_TURBO,
}
PAYOUTS: dict[str, PayoutStructure] = {
    "wta": WINNER_TAKES_ALL,
    "65-35": TOP_TWO,
    "50-30-20": TOP_THREE,
}
MULTIPLIER_TABLES: dict[str, MultiplierTable] = {
    "fair": FAIR_MULTIPLIERS,
    "realistic": REALISTIC_MULTIPLIERS,
}

DEFAULT_BUY_IN = {RunType.TOURNAMENT: 100, RunType.SPIN: 10}


@dataclass(frozen=True)
class TournamentRunConfig:
    """Everything that determines the outcome of a tournament run."""

    seats: tuple[SeatSpec, ...]
    run_type: RunType = RunType.TOURNAMENT
    tournaments: int = 1000
    tournaments_per_batch: int = 20
    structure: str | None = None
    """Key of ``STRUCTURES``; None: turbo, or hyper for a Spin & Go."""
    starting_stack: int | None = None
    buy_in: int | None = None
    payout: str | None = None
    """Key of ``PAYOUTS``; None: the default for the number of players."""
    multipliers: str = "fair"
    rebuys: bool = False
    """Rebuys during the first 3 levels at or below the starting stack, then
    an add-on of a starting stack (tournaments only)."""
    max_hands_per_tournament: int = 2000
    seed: int | None = None
    workers: int = 1
    check_invariants: bool = True
    betting: BettingRules = NO_LIMIT

    def __post_init__(self) -> None:
        if not MIN_TABLE_SEATS <= len(self.seats) <= MAX_TABLE_SEATS:
            raise ValueError(
                f"A tournament needs {MIN_TABLE_SEATS} to {MAX_TABLE_SEATS} seats."
            )

        if self.run_type == RunType.SPIN:
            if len(self.seats) != SPIN_PLAYERS:
                raise ValueError(f"A Spin & Go needs exactly {SPIN_PLAYERS} seats.")

            if self.rebuys or self.payout is not None:
                raise ValueError("A Spin & Go has no rebuys and pays by multiplier.")

        if len(set(self.seat_names)) != len(self.seats):
            raise ValueError("Seat names must be unique.")

        for name in (
            "tournaments",
            "tournaments_per_batch",
            "max_hands_per_tournament",
            "workers",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive.")

        for name, table in (
            ("structure", STRUCTURES),
            ("payout", PAYOUTS),
            ("multipliers", MULTIPLIER_TABLES),
        ):
            key = getattr(self, name)

            if key is not None and key not in table:
                raise ValueError(f"Unknown {name} {key!r}: {', '.join(table)}.")

        if self.starting_stack is not None and self.starting_stack <= 0:
            raise ValueError("The starting stack must be positive.")

        if self.buy_in is not None and self.buy_in <= 0:
            raise ValueError("The buy-in must be positive.")

    @property
    def seat_names(self) -> tuple[str, ...]:
        return seat_names(self.seats)

    @property
    def blind_structure(self) -> BlindStructure:
        default = "hyper" if self.run_type == RunType.SPIN else "turbo"

        return STRUCTURES[self.structure or default]

    @property
    def stack(self) -> int:
        if self.starting_stack is not None:
            return self.starting_stack

        if self.run_type == RunType.SPIN:
            return SPIN_STARTING_STACK

        return TOURNAMENT_STARTING_STACK

    @property
    def entry_fee(self) -> int:
        return self.buy_in or DEFAULT_BUY_IN[self.run_type]

    @property
    def multiplier_table(self) -> MultiplierTable:
        return MULTIPLIER_TABLES[self.multipliers]

    def tournament_config(self) -> TournamentConfig:
        rebuys = None

        if self.rebuys:
            rebuys = RebuyRules(
                levels=3,
                threshold=self.stack,
                rebuy_stack=self.stack,
                add_on_stack=self.stack,
            )

        return TournamentConfig(
            structure=self.blind_structure,
            starting_stack=self.stack,
            buy_in=self.entry_fee,
            payout=PAYOUTS[self.payout] if self.payout else None,
            rebuys=rebuys,
            max_hands=self.max_hands_per_tournament,
            betting=self.betting,
        )

    def with_seed(self) -> "TournamentRunConfig":
        if self.seed is not None:
            return self

        return replace(self, seed=random.SystemRandom().randrange(2**63))


# --- Playing --------------------------------------------------------------


def seating(config: TournamentRunConfig, index: int) -> list[str]:
    """Seat names in table order for tournament ``index`` (rotated)."""
    names = config.seat_names
    count = len(names)

    return [names[(seat - index) % count] for seat in range(count)]


def create_tournament(
    config: TournamentRunConfig, index: int, keep_hands: bool = False
) -> Tournament:
    """The tournament ``index`` of a run, ready to be played."""
    if config.seed is None:
        raise ValueError("The run has no seed; use config.with_seed().")

    seed = derive_seed(config.seed, "tournament", index)
    controllers = {
        name: create_bot(
            spec.bot, random.Random(derive_seed(seed, "bot", i)), spec.overrides
        )
        for i, (name, spec) in enumerate(
            zip(config.seat_names, config.seats, strict=True)
        )
    }
    names = seating(config, index)
    checker = _ChipChecker(config, index) if config.check_invariants else None
    on_hand_end = checker.check if checker else None

    if config.run_type == RunType.SPIN:
        spin = SpinConfig(
            multipliers=config.multiplier_table,
            buy_in=config.entry_fee,
            structure=config.blind_structure,
            starting_stack=config.stack,
            max_hands=config.max_hands_per_tournament,
            betting=config.betting,
        )

        return create_spin(
            spin,
            names,
            controllers,
            random.Random(derive_seed(seed, "spin")),
            keep_hands=keep_hands,
            on_hand_end=on_hand_end,
        )

    return Tournament(
        config.tournament_config(),
        names,
        controllers,
        dealer_index=derive_seed(seed, "dealer") % len(names),
        deck_rng=random.Random(derive_seed(seed, "deck")),
        keep_hands=keep_hands,
        on_hand_end=on_hand_end,
    )


class _ChipChecker:
    """Checks every hand of a tournament for chip accounting problems."""

    def __init__(self, config: TournamentRunConfig, index: int) -> None:
        self.config = config
        self.index = index
        self.hands = 0

    def check(self, hand: Hand, stacks_before: Mapping[str, int]) -> None:
        problems = find_chip_violations(hand, stacks_before)

        if problems:
            assert self.config.seed is not None
            raise InvariantError(
                message="; ".join(problems),
                seed=self.config.seed,
                hand_index=self.hands,
                session_index=self.index,
                replay_function="replay_tournament",
            )

        self.hands += 1


def run_tournament_batch(config: TournamentRunConfig, batch: Batch) -> TournamentTotals:
    """Play the complete tournaments of one batch."""
    totals = empty_totals(config)

    for index in range(batch.start, batch.start + batch.count):
        tournament = create_tournament(config, index)

        try:
            result = tournament.play_to_end()
        except Exception as error:
            if not isinstance(error, InvariantError):
                error.add_note(
                    f"Simulated tournament: seed={config.seed}, "
                    f"tournament_index={index}, hand_index={tournament.hands_played}."
                )
            raise

        record_result(totals, result)

    return totals


def record_result(totals: TournamentTotals, result: TournamentResult) -> None:
    for finish in result.finishes:
        totals.players[finish.name].record(finish)

    totals.tournaments += 1
    totals.capped += result.capped
    totals.hands += result.hands_played
    totals.levels_reached += result.level_index + 1

    if result.multiplier is not None:
        totals.multiplier_counts[result.multiplier] = (
            totals.multiplier_counts.get(result.multiplier, 0) + 1
        )


def empty_totals(config: TournamentRunConfig) -> TournamentTotals:
    count = len(config.seats)

    return TournamentTotals(
        players={
            name: TournamentPlayerStats(name=name, bot=spec.bot, seats=count)
            for name, spec in zip(config.seat_names, config.seats, strict=True)
        }
    )


def plan_tournament_batches(config: TournamentRunConfig) -> list[Batch]:
    size = config.tournaments_per_batch

    return [
        Batch(index=index, start=start, count=min(size, config.tournaments - start))
        for index, start in enumerate(range(0, config.tournaments, size))
    ]


def run_tournaments(
    config: TournamentRunConfig,
    progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
) -> "TournamentRunResult":
    """Run every tournament of the budget; progress counts tournaments."""
    config = config.with_seed()
    batches = plan_tournament_batches(config)
    started = time.perf_counter()

    results = execute_batches(
        task=partial(run_tournament_batch, config),
        batches=batches,
        units=lambda batch: batch.count,
        workers=config.workers,
        progress=progress,
        cancel=cancel,
    )
    totals = empty_totals(config)

    for batch_totals in results:
        totals.merge(batch_totals)

    return TournamentRunResult(
        config=config,
        totals=totals,
        batch_count=len(batches),
        duration_seconds=time.perf_counter() - started,
    )


def replay_tournament(
    config: TournamentRunConfig, session_index: int, hand_index: int | None = None
) -> Tournament:
    """Replay tournament ``session_index`` of a run, without chip checks.

    It stops after hand ``hand_index`` (counted from 0) when one is given,
    and keeps the hands in ``tournament.session.hands`` for inspection.
    """
    config = replace(config, check_invariants=False)
    tournament = create_tournament(config, session_index, keep_hands=True)

    while not tournament.is_finished:
        tournament.play_hand()

        if hand_index is not None and tournament.hands_played > hand_index:
            break

    return tournament


# --- Result ---------------------------------------------------------------


TOURNAMENT_CSV_COLUMNS: tuple[str, ...] = (
    "name",
    "bot",
    "tournaments",
    "wins",
    "win_rate",
    "itm_rate",
    "average_place",
    "invested",
    "prizes",
    "roi",
    "roi_ci95_low",
    "roi_ci95_high",
    "roi_without_multiplier",
    "rebuys",
    "add_ons",
)


@dataclass
class TournamentRunResult:
    config: TournamentRunConfig
    totals: TournamentTotals
    batch_count: int
    duration_seconds: float

    @property
    def players(self) -> dict[str, TournamentPlayerStats]:
        return self.totals.players

    @property
    def is_spin(self) -> bool:
        return self.config.run_type == RunType.SPIN

    @property
    def expected_multiplier(self) -> Fraction | None:
        return self.config.multiplier_table.expected_value if self.is_spin else None

    @property
    def tournaments_per_second(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0

        return self.totals.tournaments / self.duration_seconds

    def ranking(self) -> list[TournamentPlayerStats]:
        """From the best ROI to the worst; the average place breaks ties."""
        return sorted(
            self.players.values(),
            key=lambda stats: (-(stats.roi or 0.0), stats.average_place or math.inf),
        )

    def multiplier_distribution(self) -> dict[int, float]:
        total = self.totals.tournaments

        return {
            multiplier: count / total
            for multiplier, count in sorted(self.totals.multiplier_counts.items())
        }

    def player_row(self, stats: TournamentPlayerStats) -> dict[str, Any]:
        interval = stats.roi_ci95
        expected = self.expected_multiplier

        return {
            "name": stats.name,
            "bot": stats.bot,
            "tournaments": stats.tournaments,
            "wins": stats.wins,
            "win_rate": stats.win_rate,
            "itm_rate": stats.itm_rate,
            "average_place": stats.average_place,
            "invested": stats.invested,
            "prizes": stats.prizes,
            "roi": stats.roi,
            "roi_ci95_low": interval[0] if interval else None,
            "roi_ci95_high": interval[1] if interval else None,
            "roi_without_multiplier": (
                stats.roi_without_multiplier(expected) if expected else None
            ),
            "rebuys": stats.rebuys,
            "add_ons": stats.add_ons,
        }

    def to_dict(self) -> dict[str, Any]:
        expected = self.expected_multiplier

        return {
            "config": exported_config(self.config),
            "seed": self.config.seed,
            "run_type": self.config.run_type.value,
            "tournaments": self.totals.tournaments,
            "batch_count": self.batch_count,
            "capped_tournaments": self.totals.capped,
            "average_hands": self.totals.average_hands,
            "average_level": self.totals.average_level,
            "duration_seconds": self.duration_seconds,
            "multipliers": {
                str(multiplier): share
                for multiplier, share in self.multiplier_distribution().items()
            },
            "expected_multiplier": float(expected) if expected else None,
            "players": [
                {
                    **self.player_row(stats),
                    "places": stats.places,
                    "place_distribution": stats.place_distribution(),
                }
                for stats in self.players.values()
            ],
        }

    def save_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

        return path

    def save_csv(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=TOURNAMENT_CSV_COLUMNS)
            writer.writeheader()

            for stats in self.ranking():
                writer.writerow(self.player_row(stats))

        return path


# --- Summary --------------------------------------------------------------


def format_roi(stats: TournamentPlayerStats) -> str:
    """For example "+18% ROI (±6%)"."""
    if stats.roi is None:
        return "no tournament played"

    error = stats.roi_standard_error

    if error is None:
        return f"{stats.roi:+.0%} ROI"

    return f"{stats.roi:+.0%} ROI (±{CONFIDENCE_Z * error:.0%})"


def is_roi_difference_significant(
    first: TournamentPlayerStats, second: TournamentPlayerStats
) -> bool | None:
    errors = (first.roi_standard_error, second.roi_standard_error)

    if first.roi is None or second.roi is None or None in errors:
        return None

    first_error, second_error = errors
    assert first_error is not None and second_error is not None
    margin = CONFIDENCE_Z * math.hypot(first_error, second_error)

    return abs(first.roi - second.roi) > margin


def summarize_tournaments(result: TournamentRunResult) -> list[str]:
    """A few sentences about finishes and ROI (never bb/100)."""
    ranking = result.ranking()
    totals = result.totals
    count = totals.tournaments
    fair_share = 1 / len(ranking)
    best = ranking[0]
    kind = "Spin & Go games" if result.is_spin else "tournaments"
    sentences = [
        f"{best.name} won {best.wins} of {count} {kind} ({best.win_rate or 0:.0%}, "
        f"an even share is {fair_share:.0%}), finishing {best.average_place or 0:.2f} "
        f"on average: {format_roi(best)}."
    ]

    if len(ranking) > 1:
        worst = ranking[-1]
        sentences.append(
            f"{worst.name} did worst: {format_roi(worst)}, "
            f"in the money {worst.itm_rate or 0:.0%} of the time."
        )

    unclear = [
        f"{first.name} vs {second.name}"
        for first, second in zip(ranking, ranking[1:], strict=False)
        if is_roi_difference_significant(first, second) is False
    ]

    if unclear:
        sentences.append(
            "With this sample size, these ROI differences are not significant: "
            + ", ".join(unclear)
            + "."
        )

    expected = result.expected_multiplier

    if expected is not None:
        steady = max(ranking, key=lambda s: s.roi_without_multiplier(expected) or -1)
        steady_roi = steady.roi_without_multiplier(expected) or 0.0
        sentences.append(
            f"Without the multiplier draw (every game paying its expected "
            f"{float(expected):g} buy-ins), {steady.name} has the best ROI: "
            f"{steady_roi:+.0%}."
        )

    sentences.append(
        f"A {kind[:-1] if result.is_spin else 'tournament'} lasted "
        f"{totals.average_hands or 0:.0f} hands on average, reaching level "
        f"{totals.average_level or 0:.1f}."
    )

    if totals.capped:
        sentences.append(
            f"{totals.capped} {kind} reached the hand limit and were ranked by stack."
        )

    return sentences
