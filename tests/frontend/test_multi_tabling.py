"""Multi-tabling (V1.3): each game in its own window, the lobby lists them,
arranges them and brings forward the table waiting for your decision."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from backend.application.profile import ProfileStore
from frontend.components.seat_widget import SeatState
from frontend.components.table_widget import (
    TableState,
    TableWidget,
    seat_angles,
    table_scale,
)
from frontend.ui.game_window import GameWindow
from frontend.ui.main_window import MainWindow
from tests.frontend.windows import ProcessUntil, cash_setup, open_table, start_test_game


@pytest.fixture
def window(qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    window = MainWindow(save_sessions=False, profile=ProfileStore(tmp_path / "p.json"))
    yield window
    window.close()


@pytest.fixture
def brought(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> list[GameWindow]:
    """The tables brought to the front, in order (no real focus offscreen)."""
    calls: list[GameWindow] = []
    monkeypatch.setattr(window, "bring_to_front", calls.append)

    return calls


def panel_texts(window: MainWindow) -> list[str]:
    return [button.text() for button in window.main_menu.tables_panel.table_buttons]


# --- Windows ----------------------------------------------------------------------


def test_each_game_opens_in_its_own_window(window: MainWindow) -> None:
    tables = [open_table(window, key) for key in ("cash", "cash", "tournament", "spin")]

    assert window.game_windows == tables
    assert [table.number for table in tables] == [1, 2, 3, 4]
    assert all(table.isVisible() for table in tables)
    assert window.current_screen is window.main_menu
    assert tables[3].windowTitle() == "Spin & Go — Table 4"


def test_a_closed_table_frees_its_number(window: MainWindow) -> None:
    first, second, _ = (open_table(window, "cash") for _ in range(3))

    first.close()
    assert window.game_windows[0] is second

    assert open_table(window, "spin").number == 1


def test_the_lobby_lists_the_open_tables(
    window: MainWindow, brought: list[GameWindow]
) -> None:
    panel = window.main_menu.tables_panel
    assert panel.isHidden(), "no table yet: the menu looks as before"

    cash = open_table(window, "cash")
    spin = open_table(window, "spin")

    assert not panel.isHidden()
    assert panel_texts(window) == ["Cash game · Table 1", "Spin && Go · Table 2"]

    brought.clear()
    panel.table_buttons[0].click()
    assert brought == [cash]

    cash.close()
    spin.close()
    assert panel.isHidden()


def test_two_tables_play_at_once(
    window: MainWindow, process_until: ProcessUntil
) -> None:
    first, second = open_table(window, "cash"), open_table(window, "cash")
    cash_setup(first).play_button.click()
    cash_setup(second).play_button.click()

    first_game, second_game = first.table_screen.game, second.table_screen.game
    assert first_game is not None and second_game is not None
    assert first_game is not second_game

    process_until(
        lambda: (
            first_game.session.hand_number >= 1 and second_game.session.hand_number >= 1
        )
    )


# --- Your turn ----------------------------------------------------------------------


def test_the_table_waiting_for_you_is_highlighted_and_brought_forward(
    window: MainWindow, brought: list[GameWindow], process_until: ProcessUntil
) -> None:
    table = open_table(window, "cash")
    brought.clear()

    start_test_game(table, process_until)

    assert table.your_turn
    assert table.windowTitle().startswith("Your turn · ")
    assert table.screens.property("yourTurn") is True
    assert window.waiting_tables == [table]
    assert brought == [table]
    assert panel_texts(window) == ["● Cash game · Table 1"]
    assert window.main_menu.tables_panel.table_buttons[0].property("yourTurn")

    table.table_screen.action_panel.fold_button.click()

    assert not table.your_turn
    assert not table.windowTitle().startswith("Your turn")
    assert window.waiting_tables == []
    assert panel_texts(window) == ["Cash game · Table 1"]


def test_once_you_acted_the_next_waiting_table_comes_forward(
    window: MainWindow, brought: list[GameWindow], process_until: ProcessUntil
) -> None:
    first, second = open_table(window, "cash"), open_table(window, "cash")
    start_test_game(first, process_until)
    start_test_game(second, process_until)
    assert window.waiting_tables == [first, second], "the longest waiting first"
    brought.clear()

    first.table_screen.action_panel.fold_button.click()

    assert window.waiting_tables == [second]
    assert brought == [second]


def test_a_paused_table_no_longer_waits(
    window: MainWindow, process_until: ProcessUntil
) -> None:
    table = open_table(window, "cash")
    start_test_game(table, process_until)

    table.table_screen.toggle_pause()
    assert window.waiting_tables == [] and not table.your_turn

    table.table_screen.toggle_pause()
    assert window.waiting_tables == [table]


def test_the_table_stays_put_when_the_setting_is_off(
    window: MainWindow, brought: list[GameWindow], process_until: ProcessUntil
) -> None:
    window.profile.settings.table_to_front = False
    table = open_table(window, "cash")
    brought.clear()

    start_test_game(table, process_until)

    assert window.waiting_tables == [table], "still highlighted in the lobby"
    assert brought == []


def test_closing_a_waiting_table_forgets_it(
    window: MainWindow, process_until: ProcessUntil
) -> None:
    table = open_table(window, "cash")
    start_test_game(table, process_until)

    table.close()

    assert window.waiting_tables == []
    assert window.game_windows == []


# --- Arranging the tables -----------------------------------------------------------


def test_tile_arranges_the_tables_side_by_side(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(window, "_screen_area", lambda: QRect(0, 0, 3840, 2160))
    tables = [open_table(window, "cash") for _ in range(4)]

    window.main_menu.tables_panel.tile_button.click()

    frames = [table.frameGeometry() for table in tables]
    assert [(frame.x(), frame.y()) for frame in frames] == [
        (0, 0),
        (1920, 0),
        (0, 1080),
        (1920, 1080),
    ]
    assert all(frame.width() <= 1920 and frame.height() <= 1080 for frame in frames)


def test_cascade_stacks_the_tables(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(window, "_screen_area", lambda: QRect(0, 0, 1920, 1080))
    tables = [open_table(window, "tournament") for _ in range(3)]

    window.main_menu.tables_panel.cascade_button.click()

    assert [table.pos().x() for table in tables] == [0, 32, 64]
    assert [table.pos().y() for table in tables] == [0, 32, 64]


# --- The table at nine seats and in a small window ---------------------------------


def test_the_seats_are_spaced_evenly_along_the_rim() -> None:
    assert seat_angles(2, 400, 200)[0] == pytest.approx(3.14159 / 2)

    angles = seat_angles(9, 400, 150)
    assert len(angles) == 9
    assert all(
        after > before for before, after in zip(angles, angles[1:], strict=False)
    )
    # A wide table gets more seats along its long sides than at its ends.
    left_end = sum(1 for angle in angles if abs(angle - 3.14159) < 0.5)
    assert left_end <= 1


def test_the_table_shrinks_in_a_small_window_and_at_a_full_ring() -> None:
    assert table_scale(1200, 700, 6) == 1.0
    assert table_scale(1200, 700, 9) < 1.0
    assert table_scale(600, 300, 6) < table_scale(900, 500, 6)
    assert table_scale(100, 100, 9) == pytest.approx(0.55), "never unreadable"


@pytest.mark.parametrize(("width", "height"), [(1100, 640), (900, 300)])
def test_nine_seats_never_overlap(qapp: QApplication, width: int, height: int) -> None:
    table = TableWidget()
    table.resize(width, height)
    seats = tuple(
        SeatState(name=f"P{i}", stack=1000, cards=(), cards_face_up=False, status="")
        for i in range(9)
    )
    table.set_state(
        TableState(seats=seats, bets=(0,) * 9, dealer_seat=0, community_cards=(), pot=0)
    )

    rects = [seat.geometry() for seat in table.seat_widgets]

    for index, rect in enumerate(rects):
        for other in rects[index + 1 :]:
            assert not rect.intersects(other)
