"""Bot Arena tournament and Spin & Go runs: stats, determinism, CLI."""

import io
import json
import math
from collections.abc import Callable
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from backend.application.tournament import Finish
from backend.simulation import tournament_runner
from backend.simulation.cli import main
from backend.simulation.config import SeatSpec
from backend.simulation.invariants import InvariantError
from backend.simulation.tournament_runner import (
    RunType,
    TournamentRunConfig,
    create_tournament,
    replay_tournament,
    run_tournaments,
    seating,
    summarize_tournaments,
)
from backend.simulation.tournament_stats import TournamentPlayerStats

FOUR = tuple(SeatSpec(bot) for bot in ("nit", "tag", "lag", "maniac"))
THREE = tuple(SeatSpec(bot) for bot in ("tag", "lag", "maniac"))


def tournament_config(**options: object) -> TournamentRunConfig:
    defaults: dict[str, object] = {"seats": FOUR, "tournaments": 24, "seed": 5}
    defaults.update(options)

    return TournamentRunConfig(**defaults)  # type: ignore[arg-type]


def spin_config(**options: object) -> TournamentRunConfig:
    return tournament_config(
        seats=THREE, run_type=RunType.SPIN, tournaments=40, **options
    )


ConfigFactory = Callable[..., TournamentRunConfig]


def comparable(result: tournament_runner.TournamentRunResult) -> dict[str, object]:
    data = result.to_dict()
    del data["duration_seconds"], data["config"], data["batch_count"]

    return data


# --- Determinism and merging ---------------------------------------------


@pytest.mark.parametrize("make", [tournament_config, spin_config], ids=["mtt", "spin"])
def test_batch_size_does_not_change_the_results(make: ConfigFactory) -> None:
    small = run_tournaments(make(tournaments_per_batch=3))
    large = run_tournaments(make(tournaments_per_batch=100))

    assert small.batch_count > 1 and large.batch_count == 1
    assert comparable(small) == comparable(large)


@pytest.mark.parametrize("make", [tournament_config, spin_config], ids=["mtt", "spin"])
def test_one_and_several_workers_give_identical_results(
    make: ConfigFactory,
) -> None:
    one = run_tournaments(make(tournaments_per_batch=4))
    several = run_tournaments(make(tournaments_per_batch=4, workers=3))

    assert comparable(one) == comparable(several)


def test_merged_totals_add_up() -> None:
    result = run_tournaments(tournament_config(rebuys=True))
    totals = result.totals

    assert totals.tournaments == 24
    assert all(stats.tournaments == 24 for stats in result.players.values())
    # Every tournament has exactly one finish per place.
    for place in range(4):
        assert sum(stats.places[place] for stats in result.players.values()) <= 24
    assert sum(stats.wins for stats in result.players.values()) >= 24
    prizes = sum(stats.prizes for stats in result.players.values())
    invested = sum(stats.invested for stats in result.players.values())
    assert prizes == invested  # Rebuys and add-ons all go to the prize pool.


def test_spin_runs_count_the_multipliers_drawn() -> None:
    result = run_tournaments(spin_config())

    assert sum(result.totals.multiplier_counts.values()) == 40
    assert math.isclose(sum(result.multiplier_distribution().values()), 1)
    assert result.expected_multiplier == 3


# --- Seats ----------------------------------------------------------------


def test_seats_rotate_so_every_bot_sits_everywhere() -> None:
    config = tournament_config()
    names = config.seat_names
    seats_of = {name: set() for name in names}

    for index in range(len(names)):
        for seat, name in enumerate(seating(config, index)):
            seats_of[name].add(seat)

    assert seating(config, 0) == list(names)
    assert seating(config, 1) == [names[-1], *names[:-1]]
    assert all(seats == {0, 1, 2, 3} for seats in seats_of.values())


def test_every_tournament_is_seeded_from_its_index() -> None:
    config = tournament_config()

    first = create_tournament(config, 7).play_to_end()
    again = create_tournament(config, 7).play_to_end()
    other = create_tournament(config, 8).play_to_end()

    assert first == again
    assert first != other


# --- Stats on hand-built results -----------------------------------------


def finish(place: int, prize: int, invested: int = 100) -> Finish:
    return Finish(
        name="Bot", place=place, prize=prize, invested=invested, eliminated_on_hand=1
    )


def test_roi_itm_and_places_from_known_finishes() -> None:
    stats = TournamentPlayerStats(name="Bot", bot="tag", seats=4)

    for result in (finish(1, 260), finish(2, 140), finish(3, 0), finish(4, 0)):
        stats.record(result)

    assert stats.win_rate == 0.25
    assert stats.itm_rate == 0.5
    assert stats.average_place == 2.5
    assert stats.places == [1, 1, 1, 1]
    assert stats.profit == 0
    assert stats.roi == 0
    # Profits 160, 40, -100, -100 per 100 invested: ROI standard error is
    # the standard error of the mean profit divided by the buy-in.
    profits = [160, 40, -100, -100]
    mean = sum(profits) / 4
    deviation = math.sqrt(sum((p - mean) ** 2 for p in profits) / 3)
    assert stats.roi_standard_error == pytest.approx(deviation / 2 / 100)
    interval = stats.roi_ci95
    assert interval is not None and interval[0] < 0 < interval[1]


def test_roi_counts_rebuys_and_add_ons_in_the_investment() -> None:
    stats = TournamentPlayerStats(name="Bot", bot="lag", seats=3)

    stats.record(finish(1, 600, invested=300))  # Buy-in, rebuy and add-on.
    stats.record(finish(3, 0, invested=100))

    assert stats.invested == 400
    assert stats.roi == pytest.approx((600 - 400) / 400)


def test_roi_without_the_multiplier_uses_the_expected_prize_pool() -> None:
    stats = TournamentPlayerStats(name="Bot", bot="tag", seats=3)

    for place in (1, 2, 3, 1):
        stats.record(finish(place, 0, invested=10))

    # Wins half the games, each worth 3 buy-ins on average: +50%.
    assert stats.roi_without_multiplier(Fraction(3)) == pytest.approx(0.5)
    error = stats.roi_without_multiplier_error(Fraction(3))
    assert error == pytest.approx(3 * math.sqrt(0.25 / 4))


def test_merging_is_exact() -> None:
    first = TournamentPlayerStats(name="Bot", bot="tag", seats=3)
    second = TournamentPlayerStats(name="Bot", bot="tag", seats=3)
    both = TournamentPlayerStats(name="Bot", bot="tag", seats=3)
    results = [finish(1, 30, 10), finish(3, 0, 10), finish(2, 0, 10)]

    first.record(results[0])
    second.record(results[1])
    second.record(results[2])
    first.merge(second)

    for result in results:
        both.record(result)

    assert first == both


# --- Chip checks ----------------------------------------------------------


def test_a_chip_violation_stops_the_run_with_a_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*_: object) -> list[str]:
        return ["chips are not conserved"]

    monkeypatch.setattr(tournament_runner, "find_chip_violations", broken)

    with pytest.raises(InvariantError) as error:
        run_tournaments(tournament_config(tournaments=2))

    assert error.value.session_index == 0
    assert error.value.hand_index == 0
    assert "replay_tournament(config, session_index=0, hand_index=0)" in str(
        error.value
    )


def test_replay_plays_the_same_hands() -> None:
    config = tournament_config()

    replayed = replay_tournament(config, session_index=3, hand_index=4)
    full = create_tournament(config, 3, keep_hands=True)

    for _ in range(5):
        full.play_hand()

    assert replayed.hands_played == 5
    assert [h.actions for h in replayed.session.hands] == [
        h.actions for h in full.session.hands
    ]


# --- Summary and validation -----------------------------------------------


def test_the_summary_talks_in_finishes_and_roi() -> None:
    sentences = summarize_tournaments(run_tournaments(spin_config()))
    text = " ".join(sentences)

    assert "ROI" in text and "Spin & Go games" in text
    assert "bb/100" not in text
    assert "Without the multiplier draw" in text


def test_invalid_runs_are_rejected() -> None:
    with pytest.raises(ValueError, match="exactly 3"):
        TournamentRunConfig(seats=FOUR, run_type=RunType.SPIN)

    with pytest.raises(ValueError, match="no rebuys"):
        replace(spin_config(), rebuys=True)

    with pytest.raises(ValueError, match="Unknown structure"):
        tournament_config(structure="slow")

    with pytest.raises(ValueError):
        tournament_config(tournaments=0)


# --- Command line ---------------------------------------------------------


def run_cli(*args: str) -> str:
    out = io.StringIO()

    assert main(list(args), out) == 0

    return out.getvalue()


def test_cli_tournament_prints_places_and_exports(tmp_path: Path) -> None:
    output = run_cli(
        "tournament",
        "--seats",
        "nit,tag,lag,maniac",
        "--tournaments",
        "12",
        "--payout",
        "50-30-20",
        "--rebuys",
        "--seed",
        "1",
        "--workers",
        "1",
        "--output",
        str(tmp_path),
    )

    assert "ITM %" in output and "#4" in output and "ROI" in output
    data = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert data["tournaments"] == 12 and data["run_type"] == "tournament"
    assert (tmp_path / "players.csv").exists()


def test_cli_spin_reports_the_multipliers() -> None:
    output = run_cli(
        "spin",
        "--seats",
        "tag,lag,maniac",
        "--tournaments",
        "20",
        "--multipliers",
        "realistic",
        "--seed",
        "2",
        "--workers",
        "1",
        "--no-export",
    )

    assert "Multipliers drawn" in output and "ROI no mult." in output
