"""The equity calculator: cards picked with the mouse, ranges, presets."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from backend.application.ranges import PRESET_RANGES, HandRange
from frontend.formatting import parse_cards
from frontend.ui.equity_screen import EquityScreen


def screen_with_size() -> EquityScreen:
    screen = EquityScreen()
    screen.resize(1280, 800)
    screen.show()

    return screen


# --- Picking cards -----------------------------------------------------------------


def test_cards_are_picked_with_the_mouse(qapp: QApplication) -> None:
    screen = screen_with_size()
    first, second = screen.rows[0].slots
    assert screen.active_slot is first, "the first place is ready"

    QTest.mouseClick(screen.picker.cards["AH"], Qt.MouseButton.LeftButton)
    assert first.card == "AH"
    assert screen.active_slot is second, "on to the next empty place"

    QTest.mouseClick(screen.picker.cards["KH"], Qt.MouseButton.LeftButton)
    assert screen.rows[0].cards == ["AH", "KH"]
    assert screen.active_slot is screen.rows[1].slots[0]
    assert screen.picker.is_used("AH") and screen.picker.is_used("KH")

    QTest.mouseClick(screen.picker.cards["AH"], Qt.MouseButton.LeftButton)
    assert screen.rows[1].slots[0].card is None, "a used card cannot be picked"


def test_a_board_card_is_picked_and_a_place_emptied(qapp: QApplication) -> None:
    screen = screen_with_size()
    board = screen.board_slots[0]

    QTest.mouseClick(board, Qt.MouseButton.LeftButton)
    assert screen.active_slot is board
    QTest.mouseClick(screen.picker.cards["2C"], Qt.MouseButton.LeftButton)
    assert board.card == "2C"

    QTest.mouseClick(board, Qt.MouseButton.RightButton)
    assert board.card is None
    assert not screen.picker.is_used("2C")


def test_equity_on_the_flop_is_exact(qapp: QApplication) -> None:
    screen = EquityScreen()
    screen.set_hand(0, "Ah Ad")
    screen.set_hand(1, "Kc Ks")
    screen.set_board("2c 7d 9h")

    screen.calculate()
    screen.run_to_end()

    assert screen.status_label.text() == "Exact: 990 of 990 boards counted"
    aces, kings = screen.rows
    assert aces.equity_label.text() == "91.6%"
    assert kings.equity_label.text() == "8.4%"


def test_an_empty_hand_is_a_random_hand(qapp: QApplication) -> None:
    screen = EquityScreen()
    screen.seed = 4
    screen.set_hand(0, "A♠ A♦")

    screen.calculate()
    assert screen.is_running and screen.stop_button.isEnabled()
    screen.run_to_end()

    assert screen.status_label.text().startswith("Estimate: 60 000 random deals")
    equity = float(screen.rows[0].equity_label.text().split("%")[0])
    assert equity == pytest.approx(85.2, abs=1.5)


def test_one_card_is_not_a_hand(qapp: QApplication) -> None:
    screen = EquityScreen()
    screen.set_hand(0, "Ah")

    screen.calculate()

    assert "Player 1: choose two cards" in screen.error_label.text()
    assert not screen.is_running


# --- Ranges ------------------------------------------------------------------------


def test_a_range_is_painted_on_the_grid(qapp: QApplication) -> None:
    screen = screen_with_size()
    row = screen.rows[1]
    row.mode_combo.setCurrentText("Range")
    assert screen.range_row is row
    assert screen.side_stack.currentIndex() == 1
    grid = screen.range_grid

    start = grid.cell_rect("AA").center().toPoint()
    end = grid.cell_rect("QQ").center().toPoint()
    QTest.mousePress(grid, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(grid, grid.cell_rect("KK").center().toPoint())
    QTest.mouseMove(grid, end)
    QTest.mouseRelease(grid, Qt.MouseButton.LeftButton, pos=end)

    assert row.range.labels == {"AA", "KK", "QQ"}
    assert row.range_edit.text() == "QQ+"
    assert row.range_info.text() == "18 combos  ·  1.4%"

    QTest.mouseClick(grid, Qt.MouseButton.LeftButton, pos=start)
    assert row.range.labels == {"KK", "QQ"}


def test_a_preset_range_is_chosen(qapp: QApplication) -> None:
    screen = screen_with_size()
    screen.set_range(1, "AA")
    name = "BB vs BTN open — 3-bet"

    screen.preset_combo.setCurrentText(name)
    screen.preset_combo.activated.emit(screen.preset_combo.currentIndex())

    expected = HandRange.parse(PRESET_RANGES[name])
    assert screen.rows[1].range == expected
    assert screen.range_grid.labels() == expected.labels


def test_a_range_is_typed_in_notation(qapp: QApplication) -> None:
    screen = screen_with_size()
    screen.set_range(1, "AA")
    row = screen.rows[1]

    row.range_edit.setText("TT+, AKs")
    row.range_edit.editingFinished.emit()

    assert row.range.combo_count == 5 * 6 + 4
    assert screen.range_grid.labels() == row.range.labels

    row.range_edit.setText("ZZ+")
    row.range_edit.editingFinished.emit()
    assert "not a hand of a range" in screen.error_label.text()


def test_a_hand_against_a_range(qapp: QApplication) -> None:
    screen = EquityScreen()
    screen.set_hand(0, "Ah Ad")
    screen.set_range(1, "KK")
    screen.set_board("2c 7d 9h Qs")

    screen.calculate()
    screen.run_to_end()

    assert screen.status_label.text() == "Exact: 264 of 264 deals counted"
    assert screen.rows[0].equity_label.text() == f"{42 / 44:.1%}"


def test_an_empty_range_is_explained(qapp: QApplication) -> None:
    screen = EquityScreen()
    screen.set_hand(0, "Ah Ad")
    screen.set_range(1, "")

    screen.calculate()

    assert "Player 2: the range is empty" in screen.error_label.text()


def test_a_range_blocked_by_the_cards_is_explained(qapp: QApplication) -> None:
    screen = EquityScreen()
    screen.set_hand(0, "Ah Ad")
    screen.set_range(1, "AA")
    screen.set_board("As Ac 2d")

    screen.calculate()

    assert "no combination of its range is left" in screen.error_label.text()


# --- Players and results -----------------------------------------------------------


def test_players_can_be_added_and_removed(qapp: QApplication) -> None:
    screen = EquityScreen()
    assert len(screen.rows) == 2
    assert not screen.rows[0].remove_button.isEnabled()

    for _ in range(9):
        screen.add_button.click()

    assert len(screen.rows) == 9
    assert not screen.add_button.isEnabled()

    screen.rows[2].remove_button.click()
    assert len(screen.rows) == 8
    assert screen.rows[-1].label.text() == "Player 8"


def test_a_change_makes_the_results_stale(qapp: QApplication) -> None:
    screen = EquityScreen()
    screen.set_hand(0, "Ah Ad")
    screen.set_hand(1, "Kc Ks")
    screen.set_board("2c 7d 9h")
    screen.calculate()
    screen.run_to_end()

    screen.set_board("2c 7d 9h Qs")

    assert screen.rows[0].equity_label.text() == "—"
    assert screen.status_label.text() == ""


def test_clear_starts_again(qapp: QApplication) -> None:
    screen = EquityScreen()
    screen.set_hand(0, "Ah Ad")
    screen.set_range(2, "QQ+")
    screen.set_board("2c 7d 9h")

    screen.clear_button.click()

    assert len(screen.rows) == 2
    assert all(not row.is_range and not row.cards for row in screen.rows)
    assert all(slot.card is None for slot in screen.board_slots)
    assert screen.side_stack.currentIndex() == 0


def test_the_equity_screen_runs_on_the_event_loop(qapp: QApplication) -> None:
    screen = EquityScreen()
    screen.seed = 1
    screen.set_range(0, "QQ+, AKs")

    screen.calculate()
    QTest.qWait(60)

    assert screen.calculator is not None and screen.calculator.boards > 0
    screen.stop()
    assert not screen.is_running


# --- Card spelling (set_hand) ------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "cards"),
    [
        ("AsKd", ("AS", "KD")),
        ("as kd", ("AS", "KD")),
        ("A♠ K♦", ("AS", "KD")),
        ("10h, 9h", ("TH", "9H")),
        ("", ()),
    ],
)
def test_cards_are_read_in_every_usual_spelling(
    text: str, cards: tuple[str, ...]
) -> None:
    assert parse_cards(text) == cards


@pytest.mark.parametrize("text", ["A", "Ax", "1s", "AsAs"])
def test_unreadable_cards_are_refused(text: str) -> None:
    with pytest.raises(ValueError):
        parse_cards(text)


def test_the_grid_finds_the_hand_under_the_mouse(qapp: QApplication) -> None:
    screen = screen_with_size()
    grid = screen.range_grid
    screen.set_range(0, "")

    assert grid.label_at(grid.cell_rect("AKs").center()) == "AKs"
    assert grid.label_at(grid.cell_rect("AKo").center()) == "AKo"
    assert grid.label_at(QPoint(-5, -5).toPointF()) is None
