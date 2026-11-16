"""Duplicate mode, matchups, sweeps, cancellation and the command line."""

import io
import json
import multiprocessing
import threading
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from backend.poker_engine.models import Hand
from backend.simulation.cli import main
from backend.simulation.config import SeatSpec, SimulationConfig
from backend.simulation.events import HandObserver
from backend.simulation.matchup import run_matchups, run_sweep
from backend.simulation.runner import (
    SimulationCancelled,
    plan_batches,
    replay_hand,
    run_simulation,
)
from tests.simulation.helpers import AttachObserver


def duplicate_config(**options: object) -> SimulationConfig:
    defaults: dict[str, object] = {
        "seats": (SeatSpec("tag"), SeatSpec("maniac"), SeatSpec("station")),
        "hands": 60,
        "batch_size": 30,
        "seed": 12,
        "duplicate": True,
    }
    defaults.update(options)

    return SimulationConfig(**defaults)  # type: ignore[arg-type]


class DealRecorder(HandObserver):
    """Records what every seat was dealt, and who sat there."""

    def __init__(self) -> None:
        self.hands: list[dict[str, object]] = []

    def on_hand_start(self, hand: Hand) -> None:
        players = hand.table.players
        self.hands.append(
            {
                "seat_cards": [tuple(player.hand) for player in players],
                "seated": [player.name for player in players],
                "deck": tuple(hand.deck.cards),
                "dealer": hand.table.dealer_index,
            }
        )

    def on_hand_end(self, hand: Hand, stacks_before: Mapping[str, int]) -> None:
        pass


# --- Duplicate mode ----------------------------------------------------------


def test_duplicate_mode_deals_every_deal_once_per_seat_rotation(
    attach_observer: AttachObserver,
) -> None:
    recorder = DealRecorder()
    attach_observer(recorder)
    config = duplicate_config()

    result = run_simulation(config)

    assert config.deals == 20
    assert result.totals.hands == 60
    rotations = [recorder.hands[index : index + 3] for index in range(0, 60, 3)]

    for deal in rotations:
        # Same cards and button in every seat, for every rotation.
        assert len({str(hand["seat_cards"]) for hand in deal}) == 1
        assert len({hand["deck"] for hand in deal}) == 1
        assert len({hand["dealer"] for hand in deal}) == 1
        # Each bot sits once in every seat.
        for seat in range(3):
            assert {hand["seated"][seat] for hand in deal} == {  # type: ignore[index]
                "TAG",
                "Maniac",
                "Calling Station",
            }

    assert len({str(deal[0]["seat_cards"]) for deal in rotations}) == 20


def test_duplicate_rounds_the_budget_up_to_whole_deals() -> None:
    config = duplicate_config(hands=10)

    result = run_simulation(config)

    assert config.deals == 4
    assert result.totals.hands == 12
    assert result.to_dict()["deals"] == 4
    assert result.to_dict()["duplicate"] is True


def test_duplicate_keeps_rotations_of_a_deal_in_one_batch() -> None:
    batches = plan_batches(duplicate_config(hands=60, batch_size=10))

    # 10 hands per batch at 3 seats: 3 deals (9 hands) per batch.
    assert [batch.count for batch in batches] == [3, 3, 3, 3, 3, 3, 2]


def test_duplicate_results_do_not_depend_on_the_workers() -> None:
    config = duplicate_config()

    single = run_simulation(config)
    parallel = run_simulation(replace(config, workers=2))

    assert single.players == parallel.players


def test_a_duplicate_hand_can_be_replayed() -> None:
    config = duplicate_config(record_history=True)
    result = run_simulation(config)

    hand = replay_hand(config, hand_index=31)

    assert result.totals.histories[31]["payouts"] == hand.payouts


# --- Matchups and sweeps -----------------------------------------------------


def test_matchup_matrix_is_complete_and_antisymmetric() -> None:
    bots = [SeatSpec("tag"), SeatSpec("station"), SeatSpec("maniac")]
    base = SimulationConfig(seats=tuple(bots[:2]), hands=400, batch_size=200, seed=5)

    matchup = run_matchups(bots, base)

    assert matchup.names == ("TAG", "Calling Station", "Maniac")
    assert len(matchup.cells) == 6

    for row in range(3):
        assert matchup.cell(row, row) is None

        for column in range(3):
            if row != column:
                first = matchup.cell(row, column)
                second = matchup.cell(column, row)
                assert first is not None and second is not None
                assert first.bb_per_100 == pytest.approx(-(second.bb_per_100 or 0.0))
                assert first.hands == 400

    data = matchup.to_dict()
    assert data["matrix"][0][0] is None
    assert data["bots"] == ["TAG", "Calling Station", "Maniac"]


def test_a_bot_can_meet_a_copy_of_itself() -> None:
    bots = [SeatSpec("tag"), SeatSpec("tag")]
    base = SimulationConfig(seats=tuple(bots), hands=200, seed=5)

    assert run_matchups(bots, base).names == ("TAG", "TAG 2")


def test_sweep_reports_one_win_rate_per_value() -> None:
    field = [SeatSpec("station"), SeatSpec("maniac")]
    base = SimulationConfig(seats=(SeatSpec("tag"), *field), hands=300, seed=9)

    sweep = run_sweep("tag", "bluff_probability", [0.0, 0.5], field, base)

    assert [point.value for point in sweep.points] == [0.0, 0.5]
    assert all(point.win_rate.hands == 300 for point in sweep.points)
    assert sweep.points[0].result.config.seed == sweep.points[1].result.config.seed
    assert sweep.points[0].win_rate != sweep.points[1].win_rate
    assert sweep.to_dict()["parameter"] == "bluff_probability"


# --- Progress and cancellation -----------------------------------------------


@pytest.mark.parametrize("workers", [1, 2])
def test_cancellation_stops_the_run_and_its_workers(workers: int) -> None:
    cancel = threading.Event()
    reports: list[int] = []

    def on_progress(done: int, total: int) -> None:
        reports.append(done)
        cancel.set()

    config = SimulationConfig(
        seats=(SeatSpec("tag"), SeatSpec("maniac")),
        hands=20_000,
        batch_size=200,
        seed=1,
        workers=workers,
    )

    with pytest.raises(SimulationCancelled):
        run_simulation(config, progress=on_progress, cancel=cancel)

    assert 1 <= len(reports) < 100
    assert multiprocessing.active_children() == []


# --- Command line ------------------------------------------------------------


def run_cli(*args: str) -> str:
    out = io.StringIO()
    assert main(list(args), out=out) == 0
    return out.getvalue()


def test_cli_run_prints_a_summary_and_exports(tmp_path: Path) -> None:
    output = run_cli(
        "run",
        "--seats",
        "tag,maniac:Max,station",
        "--hands",
        "300",
        "--seed",
        "3",
        "--workers",
        "1",
        "--output",
        str(tmp_path),
    )

    assert "300 hands" in output
    assert "seed 3" in output
    assert "Max" in output and "VPIP" in output
    assert "won the most" in output
    data = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert data["seed"] == 3
    assert (tmp_path / "players.csv").exists()


def test_cli_elimination_and_rebuy_columns() -> None:
    elimination = run_cli(
        "run",
        "--seats",
        "tag,lag",
        "--policy",
        "elimination",
        "--sessions",
        "3",
        "--seed",
        "1",
        "--workers",
        "1",
        "--no-export",
    )
    rebuy = run_cli(
        "run",
        "--seats",
        "tag,lag",
        "--policy",
        "rebuy",
        "--hands",
        "200",
        "--seed",
        "1",
        "--workers",
        "1",
        "--no-export",
    )

    assert "Win %" in elimination and "Avg finish" in elimination
    assert "Rebuys" in rebuy


def test_cli_matchup_sweep_engine_lab_and_bots(tmp_path: Path) -> None:
    matchup = run_cli(
        "matchup",
        "--bots",
        "tag,station",
        "--hands",
        "200",
        "--seed",
        "1",
        "--workers",
        "1",
        "--output",
        str(tmp_path / "m"),
    )
    sweep = run_cli(
        "sweep",
        "--bot",
        "tag",
        "--param",
        "bluff_probability",
        "--values",
        "0,0.2",
        "--field",
        "station",
        "--hands",
        "200",
        "--seed",
        "1",
        "--workers",
        "1",
        "--no-export",
    )
    lab = run_cli(
        "engine-lab",
        "--samples",
        "2000",
        "--hands",
        "200",
        "--workers",
        "1",
        "--no-export",
    )
    bots = run_cli("bots")

    assert "heads-up" in matchup
    assert (tmp_path / "m" / "matchup.json").exists()
    assert "bluff_probability" in sweep
    assert "STRAIGHT_FLUSH" in lab and "Split pots" in lab
    assert "maniac" in bots and "Calling Station" in bots


def test_cli_rejects_duplicate_mode_with_eliminations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["run", "--seats", "tag,lag", "--policy", "elimination", "--duplicate"])

    assert exit_info.value.code == 2
    assert "Duplicate mode" in capsys.readouterr().err


def test_cli_rejects_an_unknown_bot(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["run", "--seats", "tag,genius"])

    assert "Unknown bot" in capsys.readouterr().err
