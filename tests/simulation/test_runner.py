"""Determinism, stack policies and invariant checks of the simulation runner."""

from collections.abc import Mapping
from dataclasses import replace

import pytest

from backend.poker_engine import betting
from backend.poker_engine.models import Hand, Player
from backend.simulation.config import SeatSpec, SimulationConfig, StackPolicy
from backend.simulation.events import HandObserver
from backend.simulation.invariants import InvariantError, find_chip_violations
from backend.simulation.result import SimulationResult, SimulationTotals
from backend.simulation.runner import (
    plan_batches,
    replay_hand,
    run_batch,
    run_simulation,
)
from backend.simulation.stats import PlayerStats


def make_config(*bots: str, **options: object) -> SimulationConfig:
    defaults: dict[str, object] = {"hands": 300, "batch_size": 100, "seed": 7}
    defaults.update(options)

    return SimulationConfig(
        seats=tuple(SeatSpec(bot) for bot in bots),
        **defaults,  # type: ignore[arg-type]
    )


def fingerprint(result: SimulationResult) -> dict[str, object]:
    """Everything a run produces, apart from its duration."""
    prints: dict[str, object] = {
        name: (
            stats.hands,
            stats.net_chips,
            stats.net_chips_squared,
            stats.rebuys,
            tuple(stats.finishes),
        )
        for name, stats in result.players.items()
    }
    prints["totals"] = (
        result.totals.hands,
        result.totals.sessions,
        result.totals.capped_sessions,
    )

    return prints


def assert_net_chips_sum_to_zero(players: Mapping[str, PlayerStats]) -> None:
    assert sum(stats.net_chips for stats in players.values()) == 0


# --- Batches -----------------------------------------------------------------


def test_the_hand_budget_is_split_into_fixed_size_batches() -> None:
    batches = plan_batches(make_config("basic", "basic", hands=250, batch_size=100))

    assert [(b.index, b.start, b.count) for b in batches] == [
        (0, 0, 100),
        (1, 100, 100),
        (2, 200, 50),
    ]


def test_elimination_batches_count_sessions() -> None:
    config = make_config(
        "basic",
        "basic",
        stack_policy=StackPolicy.ELIMINATION,
        sessions=25,
        sessions_per_batch=10,
    )

    assert [b.count for b in plan_batches(config)] == [10, 10, 5]


# --- Determinism -------------------------------------------------------------


def test_the_same_seed_gives_identical_results() -> None:
    config = make_config("basic", "random", "basic")

    assert fingerprint(run_simulation(config)) == fingerprint(run_simulation(config))


def test_different_seeds_give_different_results() -> None:
    first = run_simulation(make_config("basic", "random", "basic", seed=1))
    second = run_simulation(make_config("basic", "random", "basic", seed=2))

    assert fingerprint(first) != fingerprint(second)


@pytest.mark.parametrize(
    "policy",
    [StackPolicy.RESET_EACH_HAND, StackPolicy.AUTO_REBUY, StackPolicy.ELIMINATION],
)
def test_results_do_not_depend_on_the_number_of_workers(policy: StackPolicy) -> None:
    config = make_config(
        "basic",
        "random",
        "basic",
        "random",
        hands=400,
        stack_policy=policy,
        sessions=6,
        sessions_per_batch=2,
    )

    single = run_simulation(config)
    parallel = run_simulation(replace(config, workers=3))

    assert fingerprint(single) == fingerprint(parallel)


def test_a_batch_plays_the_same_hands_wherever_it_runs() -> None:
    config = make_config("basic", "random", hands=300)
    full_run = run_simulation(config)

    # Batches played separately, in reverse order, merge into the full run.
    merged = SimulationTotals.empty(config)
    batch_totals = {
        batch.index: run_batch(config, batch)
        for batch in reversed(plan_batches(config))
    }

    for index in sorted(batch_totals):
        merged.merge(batch_totals[index])

    assert merged.players == full_run.players
    assert merged.hands == 300


def test_a_seed_is_drawn_and_reported_when_none_is_given() -> None:
    result = run_simulation(make_config("basic", "random", hands=20, seed=None))

    assert result.config.seed is not None
    replayed = run_simulation(replace(result.config, seed=result.config.seed))
    assert fingerprint(replayed) == fingerprint(result)


def test_progress_is_reported_after_every_batch() -> None:
    reports: list[tuple[int, int]] = []

    run_simulation(
        make_config("basic", "random", hands=250),
        progress=lambda done, total: reports.append((done, total)),
    )

    assert reports == [(100, 250), (200, 250), (250, 250)]


# --- Stack policies ----------------------------------------------------------


class StackRecorder(HandObserver):
    def __init__(self) -> None:
        self.stacks: list[dict[str, int]] = []
        self.dealers: list[str] = []

    def on_hand_start(self, hand: Hand) -> None:
        self.dealers.append(hand.table.dealer.name)

    def on_hand_end(self, hand: Hand, stacks_before: Mapping[str, int]) -> None:
        self.stacks.append(dict(stacks_before))


def record_stacks(
    monkeypatch: pytest.MonkeyPatch, config: SimulationConfig
) -> StackRecorder:
    """Run one batch with a recorder attached to its table."""
    from backend.simulation import runner

    recorder = StackRecorder()
    original = runner.ArenaTable

    def table_with_recorder(*args: object, **kwargs: object) -> runner.ArenaTable:
        table = original(*args, **kwargs)  # type: ignore[arg-type]
        table.observers.append(recorder)
        return table

    monkeypatch.setattr(runner, "ArenaTable", table_with_recorder)
    run_simulation(config)

    return recorder


def test_reset_policy_starts_every_hand_with_the_starting_stack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config("basic", "random", "random", hands=200, starting_stack=500)

    recorder = record_stacks(monkeypatch, config)

    assert len(recorder.stacks) == 200
    assert all(
        stacks == dict.fromkeys(config.seat_names, 500) for stacks in recorder.stacks
    )


def test_reset_policy_moves_the_button_every_hand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config("basic", "random", "random", hands=6, batch_size=4)

    recorder = record_stacks(monkeypatch, config)

    assert recorder.dealers == ["Basic", "Random", "Random 2"] * 2


def test_reset_policy_conserves_chips_between_players() -> None:
    result = run_simulation(make_config("basic", "random", "random", hands=500))

    assert result.totals.hands == 500
    assert all(stats.hands == 500 for stats in result.players.values())
    assert all(stats.rebuys == 0 for stats in result.players.values())
    assert_net_chips_sum_to_zero(result.players)


def test_rebuy_policy_carries_stacks_and_tops_up_busted_players(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(
        "random",
        "random",
        "random",
        hands=300,
        stack_policy=StackPolicy.AUTO_REBUY,
        starting_stack=200,
    )

    recorder = record_stacks(monkeypatch, config)
    result = run_simulation(config)

    assert any(
        stacks != dict.fromkeys(config.seat_names, 200) for stacks in recorder.stacks
    )
    # Every hand is played by everyone: nobody stays out after busting.
    assert all(len(stacks) == 3 for stacks in recorder.stacks)
    assert sum(stats.rebuys for stats in result.players.values()) > 0
    assert_net_chips_sum_to_zero(result.players)


def test_rebuy_policy_resets_stacks_and_rotates_the_button_between_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(
        "random",
        "random",
        "random",
        hands=30,
        batch_size=10,
        stack_policy=StackPolicy.AUTO_REBUY,
    )

    recorder = record_stacks(monkeypatch, config)

    first_hands = [recorder.stacks[index] for index in (0, 10, 20)]
    assert all(
        stacks == dict.fromkeys(config.seat_names, 1000) for stacks in first_hands
    )
    assert [recorder.dealers[index] for index in (0, 10, 20)] == [
        "Random",
        "Random 2",
        "Random 3",
    ]


def test_elimination_ranks_every_player_once_per_session() -> None:
    result = run_simulation(
        make_config(
            "basic",
            "random",
            "random",
            "basic",
            stack_policy=StackPolicy.ELIMINATION,
            sessions=12,
            sessions_per_batch=5,
            starting_stack=200,
        )
    )

    assert result.totals.sessions == 12
    assert result.totals.capped_sessions == 0

    for position in range(4):
        assert sum(s.finishes[position] for s in result.players.values()) == 12

    for stats in result.players.values():
        assert sum(stats.finishes) == 12

    assert_net_chips_sum_to_zero(result.players)


def test_elimination_sessions_are_capped_and_survivors_ranked_by_stack() -> None:
    result = run_simulation(
        make_config(
            "basic",
            "basic",
            "basic",
            stack_policy=StackPolicy.ELIMINATION,
            sessions=4,
            max_hands_per_session=3,
        )
    )

    assert result.totals.capped_sessions == 4
    assert result.totals.hands == 12

    for position in range(3):
        assert sum(s.finishes[position] for s in result.players.values()) == 4


# --- Invariants --------------------------------------------------------------


def test_invariants_hold_over_ten_thousand_hands_of_random_bots() -> None:
    config = make_config(
        *["random"] * 6,
        hands=10_000,
        batch_size=1000,
        stack_policy=StackPolicy.AUTO_REBUY,
        starting_stack=300,
    )

    result = run_simulation(config)

    assert result.totals.hands == 10_000
    assert_net_chips_sum_to_zero(result.players)


@pytest.fixture
def leaking_fold_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Break the engine: a pot won by fold pays one chip too many."""
    original = betting.resolve_by_fold

    def resolve_with_an_extra_chip(hand: Hand, winner: Player) -> None:
        original(hand=hand, winner=winner)
        winner.stack += 1

    monkeypatch.setattr(betting, "resolve_by_fold", resolve_with_an_extra_chip)


@pytest.mark.usefixtures("leaking_fold_wins")
def test_a_broken_invariant_is_reported_with_its_seed_and_hand_index() -> None:
    config = make_config("random", "random", "random", seed=123)

    with pytest.raises(InvariantError) as error_info:
        run_simulation(config)

    error = error_info.value
    assert error.seed == 123
    assert error.session_index is None
    assert "seed=123" in str(error)
    assert f"hand_index={error.hand_index}" in str(error)
    assert "chips are not conserved" in str(error)

    # The reported hand is the first broken one, and replays identically.
    broken_hand = replay_hand(config, hand_index=error.hand_index)
    assert broken_hand.winner_by_fold is not None

    for earlier_index in range(error.hand_index):
        assert replay_hand(config, hand_index=earlier_index).winner_by_fold is None


@pytest.mark.usefixtures("leaking_fold_wins")
def test_a_broken_invariant_in_elimination_mode_reports_its_session() -> None:
    config = make_config(
        "random", "random", stack_policy=StackPolicy.ELIMINATION, sessions=3
    )

    with pytest.raises(InvariantError) as error_info:
        run_simulation(config)

    assert error_info.value.session_index == 0
    assert "session_index=0" in str(error_info.value)


def test_replaying_a_hand_reproduces_it_exactly() -> None:
    config = make_config("basic", "random", "basic", hands=300, record_history=True)
    result = run_simulation(config)

    for hand_index in (0, 150, 299):
        hand = replay_hand(config, hand_index=hand_index)
        recorded = result.totals.histories[hand_index]

        assert recorded["hand_number"] == hand_index + 1
        assert [p["hole_cards"] for p in recorded["players"]] == [
            player.hand for player in hand.table.players
        ]
        assert len(recorded["actions"]) == len(hand.actions)
        assert recorded["payouts"] == hand.payouts


def test_a_replayed_hand_satisfies_the_invariants() -> None:
    config = make_config("basic", "random", "basic")

    hand = replay_hand(config, hand_index=42)

    stacks_before = dict.fromkeys(config.seat_names, config.starting_stack)
    assert find_chip_violations(hand, stacks_before) == []


def test_history_is_only_kept_when_requested() -> None:
    assert run_simulation(make_config("basic", "random")).totals.histories == []

    recorded = run_simulation(make_config("basic", "random", record_history=True))
    assert len(recorded.totals.histories) == 300
