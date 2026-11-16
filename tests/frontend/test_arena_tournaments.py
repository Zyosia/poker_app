"""Tournament and Spin & Go runs in the Bot Arena, and the bar chart."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QTableWidget

from backend.simulation.config import SeatSpec, SimulationConfig
from backend.simulation.tournament_runner import (
    RunType,
    TournamentRunConfig,
    TournamentRunResult,
    run_tournaments,
)
from frontend.components.bar_chart import BarChart
from frontend.ui.arena_results_screen import ArenaResultsScreen
from frontend.ui.arena_setup_screen import ArenaSetupScreen
from frontend.ui.main_window import MainWindow
from tests.frontend.test_bot_arena import wait_until


def header_labels(table: QTableWidget) -> list[str]:
    items = (
        table.horizontalHeaderItem(column) for column in range(table.columnCount())
    )

    return [item.text() for item in items if item is not None]


@pytest.fixture
def window(qapp: QApplication) -> Iterator[MainWindow]:
    window = MainWindow(save_sessions=False)
    yield window
    window.close()


def test_run_types_show_their_own_settings(qapp: QApplication) -> None:
    setup = ArenaSetupScreen()
    form = setup.form

    assert form.isRowVisible(setup.hands_row)
    assert not form.isRowVisible(setup.tournaments_spin)
    assert setup.watch_button.isEnabled()

    setup.set_run_type(RunType.TOURNAMENT)

    assert not form.isRowVisible(setup.hands_row)
    assert not form.isRowVisible(setup.blinds_combo)
    assert form.isRowVisible(setup.tournaments_spin)
    assert form.isRowVisible(setup.structure_combo)
    assert form.isRowVisible(setup.payout_combo)
    assert not form.isRowVisible(setup.multipliers_combo)
    assert not setup.watch_button.isEnabled()
    assert "main menu" in setup.watch_button.toolTip()

    setup.set_run_type(RunType.SPIN)

    assert form.isRowVisible(setup.multipliers_combo)
    assert not form.isRowVisible(setup.structure_combo)

    setup.set_run_type(None)

    assert isinstance(setup.current_config(), SimulationConfig)


def test_setup_builds_a_tournament_configuration(qapp: QApplication) -> None:
    setup = ArenaSetupScreen()
    setup.set_seats(("nit", "tag", "lag", "maniac"))
    setup.set_run_type(RunType.TOURNAMENT)
    setup.tournaments_spin.setValue(250)
    setup.structure_combo.setCurrentIndex(setup.structure_combo.findData("deep"))
    setup.payout_combo.setCurrentIndex(setup.payout_combo.findData("50-30-20"))
    setup.rebuys_check.setChecked(True)
    setup.seed_edit.setText("9")

    config = setup.current_config()

    assert isinstance(config, TournamentRunConfig)
    assert config.run_type == RunType.TOURNAMENT
    assert config.tournaments == 250
    assert config.blind_structure.name == "Deep"
    assert config.payout == "50-30-20" and config.rebuys
    assert config.seed == 9


def test_a_spin_and_go_needs_three_seats(qapp: QApplication) -> None:
    setup = ArenaSetupScreen()
    setup.set_seats(("tag", "lag", "maniac", "nit"))
    setup.set_run_type(RunType.SPIN)

    setup.run_button.click()

    assert "exactly 3" in setup.error_label.text()


def test_a_tournament_run_goes_from_setup_to_results(window: MainWindow) -> None:
    window.main_menu.card("arena").click()
    setup = window.arena_setup_screen
    setup.set_seats(("nit", "tag", "lag", "maniac"))
    setup.set_run_type(RunType.TOURNAMENT)
    setup.tournaments_spin.setValue(12)
    setup.workers_spin.setValue(1)
    setup.seed_edit.setText("3")

    setup.run_button.click()

    assert window.arena_progress_screen.progress_bar.format().endswith("tournaments")
    wait_until(lambda: window.current_screen is window.arena_results_screen)

    results = window.arena_results_screen
    assert isinstance(results.result, TournamentRunResult)
    assert results.result.totals.tournaments == 12
    assert results.chart_stack.currentWidget() is results.place_chart
    assert results.place_chart.categories == ("1st", "2nd", "3rd", "4th")
    headers = header_labels(results.ranking_table)
    assert "ROI (95% CI)" in headers and "ITM %" in headers
    text = results.summary_label.text()
    assert "ROI" in text and "bb/100" not in text


def spin_result() -> TournamentRunResult:
    return run_tournaments(
        TournamentRunConfig(
            seats=tuple(SeatSpec(bot) for bot in ("tag", "lag", "maniac")),
            run_type=RunType.SPIN,
            tournaments=30,
            seed=4,
        )
    )


def test_spin_results_show_the_multipliers_and_steady_roi(qapp: QApplication) -> None:
    screen = ArenaResultsScreen()

    screen.show_result(spin_result())

    headers = header_labels(screen.ranking_table)
    assert "ROI without multiplier" in headers
    assert "MULTIPLIERS DRAWN" in screen.details_view.toPlainText()
    assert "SPIN & GO" in screen.title_label.text()


def test_a_cash_result_after_a_tournament_shows_the_chip_graph(
    qapp: QApplication,
) -> None:
    from backend.simulation.runner import run_simulation

    screen = ArenaResultsScreen()
    screen.show_result(spin_result())
    cash = run_simulation(
        SimulationConfig(seats=(SeatSpec("tag"), SeatSpec("lag")), hands=50, seed=1)
    )

    screen.show_result(cash)

    assert screen.chart_stack.currentWidget() is screen.chart
    assert screen.actions_table.rowCount() > 0


# --- Bar chart -------------------------------------------------------------


def test_bar_chart_hover_shows_every_share(qapp: QApplication) -> None:
    chart = BarChart()
    chart.resize(600, 300)
    chart.set_data(
        ("1st", "2nd", "3rd"), ("TAG", "LAG"), [[0.5, 0.3, 0.2], [0.2, 0.3, 0.5]]
    )
    group = chart.group_rect(1)

    event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(group.center()),
        QPointF(group.center()),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    chart.mouseMoveEvent(event)

    assert chart.hover_category == 1
    assert chart.tooltip_text(1) == "2nd\nTAG: 30.0%\nLAG: 30.0%"
    # A bar's height follows its value: 0.5 is the tallest of the first group.
    assert chart.bar_rect(0, 0).height() > chart.bar_rect(1, 0).height()
    chart.grab()  # Paints without error.


def test_bar_chart_rejects_mismatched_data(qapp: QApplication) -> None:
    chart = BarChart()

    with pytest.raises(ValueError):
        chart.set_data(("1st", "2nd"), ("TAG",), [[0.5]])

    chart.set_data((), (), [])
    chart.grab()
