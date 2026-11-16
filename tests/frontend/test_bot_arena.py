"""Main menu, Bot Arena screens and the line chart."""

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from backend.simulation.config import SeatSpec, SimulationConfig, StackPolicy
from backend.simulation.runner import run_simulation
from frontend.components.line_chart import LineChart, nice_step
from frontend.modes import MODES
from frontend.ui.arena_results_screen import ArenaResultsScreen
from frontend.ui.arena_setup_screen import ARENA_PRESETS, ArenaSetupScreen
from frontend.ui.arena_watch_screen import ArenaWatchScreen
from frontend.ui.main_window import MainWindow

WAIT_TIMEOUT_SECONDS = 60


def wait_until(condition: Callable[[], bool]) -> None:
    """Run the event loop until ``condition`` holds, with a real time limit.

    Background threads need wall-clock time, not only event loop turns.
    """
    deadline = time.monotonic() + WAIT_TIMEOUT_SECONDS

    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("The expected condition was never reached.")

        QTest.qWait(20)


@pytest.fixture
def window(qapp: QApplication) -> Iterator[MainWindow]:
    window = MainWindow(save_sessions=False)
    yield window
    window.close()


def open_arena(window: MainWindow, hands: int = 200) -> ArenaSetupScreen:
    window.main_menu.card("arena").click()
    setup = window.arena_setup_screen
    setup.hands_combo.setCurrentIndex(setup.hands_combo.findData("custom"))
    setup.hands_spin.setValue(hands)
    setup.workers_spin.setValue(1)
    setup.seed_edit.setText("7")

    return setup


# --- Main menu -----------------------------------------------------------------


def test_menu_shows_the_enabled_and_coming_soon_modes(window: MainWindow) -> None:
    cards = {card.mode.key: card for card in window.main_menu.cards}

    assert list(cards) == [mode.key for mode in MODES]
    assert cards["cash"].isEnabled() and cards["arena"].isEnabled()

    for key in ("tournament", "spin", "tools"):
        assert not cards[key].isEnabled()
        assert cards[key].note_label.text().startswith("Coming")

    assert cards["tournament"].note_label.text() == "Coming in V1.0"
    assert cards["spin"].note_label.text() == "Coming in V1.0"


def test_disabled_modes_do_not_open_anything(window: MainWindow) -> None:
    window.main_menu.card("tournament").click()

    assert window.current_screen is window.main_menu


def test_cash_game_still_starts_from_the_menu(window: MainWindow) -> None:
    window.game_screen.step_delay_ms = 0
    window.main_menu.card("cash").click()
    window.cash_setup_screen.play_button.click()

    game = window.game_screen.game
    assert window.current_screen is window.game_screen
    assert game is not None and game.hand is not None
    assert game.save_path is None


def test_back_returns_to_the_previous_screen_everywhere(window: MainWindow) -> None:
    window.main_menu.card("arena").click()
    assert window.current_screen is window.arena_setup_screen

    window.arena_setup_screen.back_button.click()
    assert window.current_screen is window.main_menu

    window.back()
    assert window.current_screen is window.main_menu


# --- Setup ---------------------------------------------------------------------


def test_setup_builds_the_configuration(qapp: QApplication) -> None:
    setup = ArenaSetupScreen()
    setup.set_seats(("tag", "station"))
    setup.seat_rows[1].name_edit.setText("Callie")
    setup.set_hands(10_000)
    setup.seed_edit.setText("42")
    setup.duplicate_check.setChecked(True)

    config = setup.current_config()

    assert isinstance(config, SimulationConfig)
    assert config.seats == (SeatSpec("tag"), SeatSpec("station", name="Callie"))
    assert config.hands == 10_000
    assert config.seed == 42
    assert config.duplicate is True
    assert config.stack_policy == StackPolicy.RESET_EACH_HAND


def test_a_blank_seed_means_a_random_one(qapp: QApplication) -> None:
    setup = ArenaSetupScreen()

    assert setup.current_config().seed is None


def test_presets_fill_the_seats(qapp: QApplication) -> None:
    setup = ArenaSetupScreen()
    setup.preset_combo.setCurrentIndex(
        setup.preset_combo.findData("Full styles table (6-max)")
    )

    assert (
        tuple(row.bot for row in setup.seat_rows)
        == ARENA_PRESETS["Full styles table (6-max)"]
    )
    assert not setup.add_seat_button.isEnabled()


def test_seats_stay_between_two_and_six(qapp: QApplication) -> None:
    setup = ArenaSetupScreen()
    setup.set_seats(("tag", "lag"))

    setup.remove_seat(setup.seat_rows[0])
    assert len(setup.seat_rows) == 2
    assert not setup.seat_rows[0].remove_button.isEnabled()

    for _ in range(6):
        setup.add_seat("nit")

    assert len(setup.seat_rows) == 6


def test_duplicate_toggle_is_disabled_outside_the_reset_policy(
    qapp: QApplication,
) -> None:
    setup = ArenaSetupScreen()
    setup.duplicate_check.setChecked(True)

    setup.policy_combo.setCurrentIndex(
        setup.policy_combo.findData(StackPolicy.AUTO_REBUY)
    )

    assert not setup.duplicate_check.isEnabled()
    assert not setup.duplicate_check.isChecked()
    assert "Reset each hand" in setup.duplicate_check.toolTip()

    setup.policy_combo.setCurrentIndex(
        setup.policy_combo.findData(StackPolicy.ELIMINATION)
    )
    config = setup.current_config()
    assert isinstance(config, SimulationConfig)
    assert config.stack_policy == StackPolicy.ELIMINATION


def test_invalid_settings_are_reported(qapp: QApplication) -> None:
    setup = ArenaSetupScreen()
    setup.set_seats(("tag", "lag"))
    setup.seat_rows[0].name_edit.setText("Same")
    setup.seat_rows[1].name_edit.setText("Same")
    received: list[SimulationConfig] = []
    setup.run_requested.connect(received.append)

    setup.run_button.click()

    assert received == []
    assert "unique" in setup.error_label.text()


# --- Fast run ------------------------------------------------------------------


def test_a_small_run_goes_from_setup_to_results(
    window: MainWindow, tmp_path: Path
) -> None:
    setup = open_arena(window, hands=200)
    setup.run_button.click()

    assert window.current_screen is window.arena_progress_screen
    wait_until(lambda: window.current_screen is window.arena_results_screen)

    results = window.arena_results_screen
    assert results.result is not None
    assert results.result.totals.hands == 200
    assert results.result.config.seed == 7
    assert results.ranking_table.rowCount() == len(setup.seat_rows)
    assert results.chart.series_names == tuple(setup.current_config().seat_names)
    assert results.chart.points[-1][0] == 200
    assert "won the most" in results.summary_label.text()
    assert "Seed: 7" in results.details_view.toPlainText()

    json_path = results.export(tmp_path / "result.json", "json")
    csv_path = results.export(tmp_path / "players.csv", "csv")
    assert json.loads(json_path.read_text(encoding="utf-8"))["seed"] == 7
    assert csv_path.read_text(encoding="utf-8").startswith("name,")

    # Back to setup keeps the settings.
    results.back_button.click()
    assert window.current_screen is window.arena_setup_screen
    assert setup.hands() == 200


def test_run_again_uses_the_same_seed(window: MainWindow) -> None:
    open_arena(window, hands=100).run_button.click()
    wait_until(lambda: window.current_screen is window.arena_results_screen)
    first = window.arena_results_screen.result
    assert first is not None

    window.arena_results_screen.rerun_button.click()
    wait_until(
        lambda: (
            window.current_screen is window.arena_results_screen
            and window.arena_results_screen.result is not first
        )
    )

    second = window.arena_results_screen.result
    assert second is not None
    assert second.config.seed == first.config.seed
    assert second.players == first.players

    window.arena_results_screen.back_button.click()
    assert window.current_screen is window.arena_setup_screen


def test_a_random_seed_is_shown_after_the_run(window: MainWindow) -> None:
    setup = open_arena(window, hands=50)
    setup.seed_edit.clear()
    setup.run_button.click()
    wait_until(lambda: window.current_screen is window.arena_results_screen)

    seed = window.arena_results_screen.result.config.seed  # type: ignore[union-attr]
    assert str(seed) in setup.seed_edit.placeholderText()


def test_cancelling_a_run_returns_to_the_setup(window: MainWindow) -> None:
    setup = open_arena(window, hands=1_000_000)
    setup.run_button.click()
    progress = window.arena_progress_screen
    wait_until(lambda: progress.progress_bar.value() > 0)

    progress.cancel_button.click()
    wait_until(lambda: window.current_screen is window.arena_setup_screen)

    assert not progress.is_running


# --- Watch mode ----------------------------------------------------------------


def test_watch_mode_steps_through_hands_with_the_spectator_view(
    window: MainWindow,
) -> None:
    open_arena(window, hands=3).watch_button.click()
    watch = window.arena_watch_screen
    assert window.current_screen is watch
    assert watch.hand is not None

    watch.toggle_pause()
    assert watch.is_paused and watch.step_button.isEnabled()

    seats = watch.table_widget.seat_widgets
    assert all(seat.card_widgets[0].is_face_up for seat in seats)

    watch.spectator_check.setChecked(False)
    face_up = [seat.card_widgets[0].is_face_up for seat in seats]
    assert face_up.count(True) < len(seats) or watch.hand.showdown_evaluations

    for _ in range(500):
        if watch.is_complete:
            break
        watch.step_button.click()

    assert watch.is_complete
    assert watch.hands_played == 3
    assert "All hands have been played." in watch.history_view.toPlainText()

    watch.back_button.click()
    assert window.current_screen is window.arena_setup_screen


def test_watch_mode_plays_the_same_hands_as_the_fast_run(qapp: QApplication) -> None:
    config = SimulationConfig(
        seats=(SeatSpec("tag"), SeatSpec("maniac"), SeatSpec("station")),
        hands=20,
        batch_size=8,
        seed=5,
    )
    watch = ArenaWatchScreen()
    watch.start(config)
    watch.toggle_pause()

    while not watch.is_complete:
        watch.step()

    fast = run_simulation(config)
    assert watch.hands_played == 20

    for stats in fast.players.values():
        assert f"{stats.name} {stats.net_chips:+,}".replace(",", " ") in (
            watch.standings_label.text()
        )


def test_watch_mode_runs_on_its_timer(window: MainWindow) -> None:
    setup = open_arena(window, hands=2)
    watch = window.arena_watch_screen
    watch.speed_combo.setItemData(watch.speed_combo.currentIndex(), 1)
    setup.watch_button.click()

    wait_until(lambda: watch.is_complete)

    assert watch.hands_played == 2


# --- Results and chart ---------------------------------------------------------


def test_ranking_is_sortable_by_number(qapp: QApplication) -> None:
    result = run_simulation(
        SimulationConfig(
            seats=(SeatSpec("tag"), SeatSpec("maniac"), SeatSpec("station")),
            hands=300,
            seed=2,
        )
    )
    screen = ArenaResultsScreen()
    screen.show_result(result)
    table = screen.ranking_table
    net_column = next(
        column
        for column in range(table.columnCount())
        if table.horizontalHeaderItem(column).text() == "Net chips"  # type: ignore[union-attr]
    )

    table.sortItems(net_column, Qt.SortOrder.AscendingOrder)

    names = [table.item(row, 0).text() for row in range(3)]  # type: ignore[union-attr]
    expected = [
        s.name for s in sorted(result.players.values(), key=lambda s: s.net_chips)
    ]
    assert names == expected


def test_elimination_results_show_win_rates(qapp: QApplication) -> None:
    result = run_simulation(
        SimulationConfig(
            seats=(SeatSpec("tag"), SeatSpec("lag")),
            stack_policy=StackPolicy.ELIMINATION,
            sessions=3,
            seed=2,
        )
    )
    screen = ArenaResultsScreen()
    screen.show_result(result)
    headers = [
        screen.ranking_table.horizontalHeaderItem(c).text()  # type: ignore[union-attr]
        for c in range(screen.ranking_table.columnCount())
    ]

    assert "Win %" in headers and "Avg finish" in headers
    assert "sessions" in screen.summary_label.text()


def test_line_chart_hover_shows_the_hand_and_values(qapp: QApplication) -> None:
    chart = LineChart()
    chart.resize(600, 320)
    chart.set_series(
        ["TAG", "Maniac"], [(0, (0, 0)), (500, (1200, -1200)), (1000, (900, -900))]
    )

    middle = chart.plot_rect().center()
    event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(middle.x(), middle.y()),
        QPointF(middle.x(), middle.y()),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    chart.mouseMoveEvent(event)

    assert chart.hover_index == 1
    assert chart.tooltip_text(1) == "Hand 500\nTAG: +1 200\nManiac: −1 200"
    assert not chart.grab().isNull()


def test_line_chart_handles_no_data_and_rejects_bad_points(qapp: QApplication) -> None:
    chart = LineChart()
    chart.resize(400, 260)

    assert not chart.grab().isNull()

    with pytest.raises(ValueError):
        chart.set_series(["A", "B"], [(0, (1,))])


def test_nice_steps_are_round_numbers() -> None:
    assert nice_step(1000) == 200
    assert nice_step(37) == 10
    assert nice_step(0) == 1.0
