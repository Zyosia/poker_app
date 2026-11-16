"""Execution of a simulation: batches, stack policies and worker processes.

The budget is split into batches of fixed size. All the randomness of a batch
(cards, bot decisions, starting button) derives from ``(seed, batch index)``,
or from ``(seed, session index)`` in elimination mode, so a batch plays the
same hands in any process. Batch results are merged in batch order, which
makes the results identical whatever the number of workers.
"""

import multiprocessing
import random
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from functools import partial

from backend.application.persistence import serialize_hand
from backend.bots.factory import create_bot
from backend.poker_engine.deck import Deck
from backend.poker_engine.models import Hand
from backend.poker_engine.session import GameConfig

from .config import SimulationConfig, StackPolicy, derive_seed
from .invariants import InvariantError, find_chip_violations
from .result import SimulationResult, SimulationTotals
from .stats import StatsCollector
from .table import ArenaTable

ProgressCallback = Callable[[int, int], None]
"""Called with (units done, total units); units are hands, or sessions in
elimination mode."""

CANCEL_POLL_SECONDS = 0.1

HandLocation = tuple[int | None, int]
"""(session index or None, hand index) of a hand."""


class SimulationCancelled(Exception):
    """The simulation was stopped before the end of its budget."""


@dataclass(frozen=True)
class Batch:
    """A slice of the budget: ``count`` units from ``start``.

    Units are hands, deals in duplicate mode, or sessions in elimination.
    """

    index: int
    start: int
    count: int


def plan_batches(config: SimulationConfig) -> list[Batch]:
    """Split the budget of a simulation into batches."""
    if config.stack_policy == StackPolicy.ELIMINATION:
        total, size = config.sessions, config.sessions_per_batch
    elif config.duplicate:
        # Every rotation of a deal stays in the same batch.
        total, size = config.deals, max(1, config.batch_size // len(config.seats))
    else:
        total, size = config.hands, config.batch_size

    return [
        Batch(index=index, start=start, count=min(size, total - start))
        for index, start in enumerate(range(0, total, size))
    ]


def progress_units(config: SimulationConfig, batch: Batch) -> int:
    """Hands (or sessions in elimination mode) covered by a batch."""
    if config.duplicate:
        return batch.count * len(config.seats)

    return batch.count


def run_simulation(
    config: SimulationConfig,
    progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
) -> SimulationResult:
    """Run a complete simulation.

    A seed is drawn when the configuration has none; it is part of the
    result so the run can be reproduced. Setting ``cancel`` stops the run
    (and its worker processes) and raises ``SimulationCancelled``.
    """
    config = config.with_seed()
    batches = plan_batches(config)
    total_units = sum(progress_units(config, batch) for batch in batches)
    units_done = 0
    results: dict[int, SimulationTotals] = {}
    started = time.perf_counter()

    def collect(batch: Batch, totals: SimulationTotals) -> None:
        nonlocal units_done
        results[batch.index] = totals
        units_done += progress_units(config, batch)

        if progress is not None:
            progress(units_done, total_units)

    def is_cancelled() -> bool:
        return cancel is not None and cancel.is_set()

    worker_count = min(config.workers, len(batches))

    if worker_count == 1:
        for batch in batches:
            if is_cancelled():
                raise SimulationCancelled

            collect(batch, run_batch(config, batch))
    else:
        # "spawn" behaves the same on every platform and is safe with Qt.
        context = multiprocessing.get_context("spawn")
        pool = context.Pool(processes=worker_count)

        try:
            pending = pool.imap_unordered(partial(_run_indexed_batch, config), batches)

            while len(results) < len(batches):
                if is_cancelled():
                    raise SimulationCancelled

                try:
                    batch, totals = pending.next(timeout=CANCEL_POLL_SECONDS)
                except multiprocessing.TimeoutError:
                    continue

                collect(batch, totals)
        finally:
            pool.terminate()
            pool.join()

    merged = SimulationTotals.empty(config)

    for index in sorted(results):
        merged.merge(results[index])

    return SimulationResult(
        config=config,
        totals=merged,
        batch_count=len(batches),
        duration_seconds=time.perf_counter() - started,
    )


def run_batch(config: SimulationConfig, batch: Batch) -> SimulationTotals:
    """Play one batch and return its totals."""
    schedule = BatchSchedule(config, batch)

    while (hand := schedule.start_next_hand()) is not None:
        schedule.play_current_hand(hand)
        schedule.finish_hand()

    return schedule.totals


def replay_hand(
    config: SimulationConfig,
    hand_index: int,
    session_index: int | None = None,
) -> Hand:
    """Replay one hand of a simulation exactly, without checking invariants.

    ``hand_index`` counts hands from the start of the simulation, or from the
    start of the session in elimination mode.
    """
    if config.seed is None:
        raise ValueError("Only a seeded simulation can be replayed.")

    config = replace(config, check_invariants=False)

    if config.stack_policy == StackPolicy.ELIMINATION:
        if session_index is None:
            raise ValueError("Elimination hands are located by session and hand.")
        unit = session_index
    elif config.duplicate:
        unit = hand_index // len(config.seats)
    else:
        unit = hand_index

    batch = next(
        (b for b in plan_batches(config) if b.start <= unit < b.start + b.count),
        None,
    )

    if batch is None:
        raise ValueError("The hand is outside the simulation budget.")

    schedule = BatchSchedule(config, batch)

    while (hand := schedule.start_next_hand()) is not None:
        schedule.play_current_hand(hand)

        if schedule.location == (session_index, hand_index):
            return hand

        schedule.finish_hand()

    raise ValueError("The hand was never played.")


def _run_indexed_batch(
    config: SimulationConfig, batch: Batch
) -> tuple[Batch, SimulationTotals]:
    return batch, run_batch(config, batch)


class BatchSchedule:
    """Deals the hands of one batch in order, applying the stack policy.

    The hands can be played all at once (``play_current_hand``) or step by
    step on ``table``, which is how the Bot Arena watch mode shows them:

    >>> while (hand := schedule.start_next_hand()) is not None:
    ...     while not hand.finished:
    ...         schedule.table.step()
    ...     schedule.finish_hand()
    """

    def __init__(self, config: SimulationConfig, batch: Batch) -> None:
        if config.seed is None:
            raise ValueError("The simulation has no seed; use config.with_seed().")

        self.config = config
        self.batch = batch
        self.seed = config.seed
        self.totals = SimulationTotals.empty(config)
        self.collector = StatsCollector(
            players=self.totals.players,
            engine=self.totals.engine,
            chart=self.totals.chart,
            chart_stride=config.chart_stride,
        )
        self.table: ArenaTable | None = None
        self.location: HandLocation | None = None
        self._slots = self._deal_slots()

    def require_table(self) -> ArenaTable:
        if self.table is None:
            raise RuntimeError("No hand has been started.")

        return self.table

    def start_next_hand(self) -> Hand | None:
        """Prepare the stacks and button, and deal the next hand.

        Returns None once the batch is complete.
        """
        try:
            table, deck, location = next(self._slots)
        except StopIteration:
            self.collector.add_chart_point()
            return None

        self.table = table
        self.location = location

        return self._annotated(lambda: table.start_hand(deck))

    def play_current_hand(self, hand: Hand) -> None:
        """Play the rest of the current hand."""
        table = self.require_table()

        def play() -> Hand:
            while not hand.finished:
                table.step()
            return hand

        self._annotated(play)

    def finish_hand(self) -> None:
        """Check and record the hand that just finished."""
        table = self.require_table()
        hand = table.hand
        assert hand is not None and self.location is not None
        session_index, hand_index = self.location
        self.totals.hands += 1

        if self.config.check_invariants:
            problems = find_chip_violations(hand, table.stacks_before)

            if problems:
                raise InvariantError(
                    message="; ".join(problems),
                    seed=self.seed,
                    hand_index=hand_index,
                    session_index=session_index,
                )

        if self.config.record_history:
            self.totals.histories.append(
                serialize_hand(hand, hand_number=hand_index + 1)
            )

        if self.config.stack_policy == StackPolicy.ELIMINATION:
            self._eliminate_busted_players(table)

    def _annotated(self, play: Callable[[], Hand]) -> Hand:
        """Run ``play``, adding the location of the hand to any error."""
        try:
            return play()
        except Exception as error:
            error.add_note(f"Simulated hand: seed={self.seed}, {self._describe()}.")
            raise

    def _describe(self) -> str:
        if self.location is None:
            return "before the first hand"

        session_index, hand_index = self.location
        location = f"hand_index={hand_index}"

        if session_index is not None:
            location = f"session_index={session_index}, {location}"

        return location

    # --- Stack policies ------------------------------------------------------

    def _deal_slots(self) -> Iterator[tuple[ArenaTable, Deck, HandLocation]]:
        if self.config.stack_policy == StackPolicy.ELIMINATION:
            return self._elimination_slots()

        if self.config.duplicate:
            return self._duplicate_slots()

        return self._cash_slots()

    def _create_table(self, base_seed: int) -> ArenaTable:
        """Seat the bots, each with its own random stream from ``base_seed``."""
        config = self.config
        controllers = {
            name: create_bot(
                seat.bot,
                random.Random(derive_seed(base_seed, "bot", index)),
                seat.overrides,
            )
            for index, (name, seat) in enumerate(
                zip(config.seat_names, config.seats, strict=True)
            )
        }

        return ArenaTable(
            seat_names=config.seat_names,
            controllers=controllers,
            game_config=GameConfig(
                starting_stack=config.starting_stack,
                rebuy_stack=config.starting_stack,
                small_blind=config.small_blind,
                big_blind=config.big_blind,
            ),
            observers=[self.collector],
        )

    def _cash_slots(self) -> Iterator[tuple[ArenaTable, Deck, HandLocation]]:
        """Hands with the reset or rebuy stack policy."""
        config = self.config
        batch_seed = derive_seed(self.seed, "batch", self.batch.index)
        table = self._create_table(batch_seed)
        deck_rng = random.Random(derive_seed(batch_seed, "deck"))
        seat_count = len(table.players)

        # With rebuys, stacks carry over inside the batch only; the starting
        # button rotates from one batch to the next.
        table.session.table.dealer_index = self.batch.index % seat_count

        for offset in range(self.batch.count):
            hand_index = self.batch.start + offset

            if config.stack_policy == StackPolicy.RESET_EACH_HAND:
                for player in table.players:
                    player.stack = config.starting_stack

                table.session.table.dealer_index = hand_index % seat_count
            elif offset > 0:
                for player in table.session.get_busted_players():
                    table.session.rebuy_player(player)
                    self.totals.players[player.name].rebuys += 1

                table.session.table.move_dealer()

            yield table, _deck(deck_rng), (None, hand_index)

    def _duplicate_slots(self) -> Iterator[tuple[ArenaTable, Deck, HandLocation]]:
        """Every deal once per cyclic rotation of the seats, from reset stacks.

        The cards follow the seats: in rotation ``r``, the bot listed at
        index ``i`` sits in seat ``(i + r) % n`` and receives that seat's
        cards, so every bot plays every deal from every seat.
        """
        batch_seed = derive_seed(self.seed, "batch", self.batch.index)
        table = self._create_table(batch_seed)
        deck_rng = random.Random(derive_seed(batch_seed, "deck"))
        seated = list(table.players)
        seat_count = len(seated)

        for deal_index in range(self.batch.start, self.batch.start + self.batch.count):
            deal_seed = deck_rng.getrandbits(64)

            for rotation in range(seat_count):
                table.players[:] = [
                    seated[(seat - rotation) % seat_count] for seat in range(seat_count)
                ]

                for player in table.players:
                    player.stack = self.config.starting_stack

                table.session.table.dealer_index = deal_index % seat_count
                location = (None, deal_index * seat_count + rotation)

                yield table, Deck(random.Random(deal_seed)), location

    def _elimination_slots(self) -> Iterator[tuple[ArenaTable, Deck, HandLocation]]:
        """Complete sessions, each played until one player has every chip."""
        config = self.config
        seat_count = len(config.seats)

        for session_index in range(
            self.batch.start, self.batch.start + self.batch.count
        ):
            session_seed = derive_seed(self.seed, "session", session_index)
            table = self._create_table(session_seed)
            session = table.session
            deck_rng = random.Random(derive_seed(session_seed, "deck"))
            session.table.dealer_index = (
                derive_seed(session_seed, "dealer") % seat_count
            )
            hand_index = 0

            while session.can_continue() and hand_index < config.max_hands_per_session:
                if hand_index > 0:
                    session.table.move_dealer()

                yield table, _deck(deck_rng), (session_index, hand_index)
                hand_index += 1

            if session.can_continue():
                self.totals.capped_sessions += 1

            # The survivors are ranked by stack; a capped session keeps several.
            survivors = sorted(
                session.get_players_with_chips(),
                key=lambda player: player.stack,
                reverse=True,
            )

            for position, player in enumerate(survivors, start=1):
                self.totals.players[player.name].record_finish(position, seat_count)

            self.totals.sessions += 1

    def _eliminate_busted_players(self, table: ArenaTable) -> None:
        """Eliminate the players busted in the last hand, recording their finish.

        Players busted in the same hand are ranked by their stack before it.
        """
        session = table.session
        busted = sorted(
            session.get_busted_players(),
            key=lambda player: table.stacks_before.get(player.name, 0),
            reverse=True,
        )
        position = len(session.get_players_with_chips()) + 1

        for player in busted:
            session.eliminate_player(player)
            self.totals.players[player.name].record_finish(position, len(table.players))
            position += 1


def _deck(deck_rng: random.Random) -> Deck:
    """A deck shuffled from its own seed, drawn from the batch's deck stream."""
    return Deck(random.Random(deck_rng.getrandbits(64)))
