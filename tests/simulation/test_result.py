"""Export of the results, plain-language summary and Engine Lab."""

import csv
import json
import math
from pathlib import Path

from backend.poker_engine.hand_evaluator import HandCategory
from backend.simulation.config import SeatSpec, SimulationConfig, StackPolicy
from backend.simulation.engine_lab import (
    SEVEN_CARD_CATEGORY_COUNTS,
    SEVEN_CARD_COMBINATIONS,
    check_seven_card_frequencies,
)
from backend.simulation.result import CSV_COLUMNS
from backend.simulation.runner import run_simulation
from backend.simulation.stats import PlayerStats
from backend.simulation.summary import is_difference_significant, summarize


def small_run(**options: object):  # noqa: ANN201 - test helper
    config = SimulationConfig(
        seats=(SeatSpec("tag"), SeatSpec("station"), SeatSpec("maniac")),
        hands=400,
        batch_size=200,
        seed=8,
        **options,  # type: ignore[arg-type]
    )
    return run_simulation(config)


def test_json_export_contains_the_config_seed_and_every_player(tmp_path: Path) -> None:
    result = small_run()

    path = result.save_json(tmp_path / "out" / "result.json")
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["seed"] == 8
    assert data["config"]["seed"] == 8
    assert data["config"]["stack_policy"] == "reset"
    assert data["batch_size"] == 200
    assert data["hands"] == 400
    assert [player["name"] for player in data["players"]] == [
        "TAG",
        "Calling Station",
        "Maniac",
    ]
    tag = data["players"][0]
    assert set(tag["action_frequencies"]) == {"PREFLOP", "FLOP", "TURN", "RIVER"}
    assert tag["positions"]["BTN"]["hands"] > 0
    assert data["chart"]["players"] == ["TAG", "Calling Station", "Maniac"]
    assert data["chart"]["points"][0] == [0, [0, 0, 0]]
    assert sum(data["engine_lab"]["showdown_categories"]) > 0


def test_csv_export_has_one_row_per_player_from_best_to_worst(tmp_path: Path) -> None:
    result = small_run()

    path = result.save_csv(tmp_path / "players.csv")

    with path.open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    assert tuple(rows[0]) == CSV_COLUMNS
    assert len(rows) == 3
    nets = [int(row["net_chips"]) for row in rows]
    assert nets == sorted(nets, reverse=True)


def test_summary_names_the_winner_and_flags_unclear_differences() -> None:
    result = small_run()
    best = result.ranking()[0]

    sentences = summarize(result)

    assert sentences[0].startswith(f"{best.name} won the most: ")
    assert "bb/100" in sentences[0]
    assert any("not significant" in s or "significant" in s for s in sentences)


def test_summary_of_an_elimination_run_reports_sessions_won() -> None:
    result = small_run(stack_policy=StackPolicy.ELIMINATION, sessions=6)

    sentences = summarize(result)

    assert "of 6 sessions" in sentences[0]
    assert "on average" in sentences[0]


def make_stats(name: str, results: list[int]) -> PlayerStats:
    stats = PlayerStats(name=name, bot="basic")

    for net_chips in results:
        stats.record_hand(net_chips)

    return stats


def test_significance_compares_the_win_rates_with_their_errors() -> None:
    steady_winner = make_stats("A", [12, 8] * 200)
    steady_loser = make_stats("B", [-12, -8] * 200)
    noisy = make_stats("C", [500, -480] * 5)

    assert is_difference_significant(steady_winner, steady_loser, 10) is True
    assert is_difference_significant(steady_winner, noisy, 10) is False
    assert is_difference_significant(steady_winner, make_stats("D", [1]), 10) is None


def test_theoretical_seven_card_counts_cover_every_hand() -> None:
    assert sum(SEVEN_CARD_CATEGORY_COUNTS.values()) == SEVEN_CARD_COMBINATIONS
    assert math.comb(52, 7) == 133_784_560
    assert set(SEVEN_CARD_CATEGORY_COUNTS) == set(HandCategory)


def test_evaluated_seven_card_frequencies_match_the_theory() -> None:
    report = check_seven_card_frequencies(samples=30_000, seed=1)

    assert report.samples == 30_000
    assert sum(check.observed for check in report.checks) == 30_000
    # More than 4.5 standard deviations would point to an evaluator bug.
    assert report.max_abs_z_score < 4.5
