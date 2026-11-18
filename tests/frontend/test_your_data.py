"""V2.1: imports kept, sessions deleted, all data deleted, replay at the table."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from backend.application.bankroll import DEFAULT_BALANCE
from backend.application.profile import ProfileStore, UserSettings
from frontend.ui import session_browser_screen, settings_dialog
from frontend.ui.main_window import MainWindow
from frontend.ui.replayer_window import ReplayerWindow
from frontend.ui.session_browser_screen import SessionBrowserScreen
from tests.frontend.windows import ProcessUntil, open_table, start_test_game
from tests.hand_history_text import WINAMAX_FILE
from tests.session_files import cash_session


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    cash_session(sessions / "pk_sess_20261110_100000.dat", hands=4)
    cash_session(sessions / "pk_sess_20261111_100000.dat", hands=4, seed=2)

    return sessions


@pytest.fixture
def window(qapp: QApplication, folder: Path, tmp_path: Path) -> Iterator[MainWindow]:
    window = MainWindow(
        save_sessions=False,
        session_dir=folder,
        profile=ProfileStore(tmp_path / "profile.json"),
    )
    yield window
    window.close()


@pytest.fixture
def answers(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """The answers given to the confirmations, in order (Yes by default)."""
    given: list[bool] = []

    def answer(*_args: object) -> bool:
        return given.pop(0) if given else True

    monkeypatch.setattr(session_browser_screen, "confirm_delete", answer)
    monkeypatch.setattr(settings_dialog, "confirm_delete_all", answer)

    return given


def open_browser(window: MainWindow) -> SessionBrowserScreen:
    window.main_menu.card("tools").click()
    window.tools_screen.card("sessions").click()

    return window.session_browser_screen


# --- Imported histories are kept ---------------------------------------------------


def test_an_imported_history_is_still_listed_later(
    window: MainWindow, folder: Path, tmp_path: Path
) -> None:
    path = tmp_path / "winamax.txt"
    path.write_text(WINAMAX_FILE, encoding="utf-8")
    browser = open_browser(window)
    browser.open_file(path)
    window.back_to_first()

    browser = open_browser(window)
    assert [s.source for s in browser.sessions].count("Winamax") == 1

    later = MainWindow(save_sessions=False, session_dir=folder)
    later_browser = open_browser(later)
    assert any(s.source == "Winamax" for s in later_browser.sessions)
    later.close()


# --- Deleting a session --------------------------------------------------------------


def test_a_session_is_deleted_once_confirmed(
    window: MainWindow, answers: list[bool]
) -> None:
    browser = open_browser(window)
    session = browser.session
    assert session is not None and browser.delete_button.isEnabled()

    answers.append(False)
    browser.delete_button.click()
    assert session.path.exists() and len(browser.sessions) == 2

    browser.delete_button.click()
    assert not session.path.exists()
    assert len(browser.sessions) == 1

    window.back_to_first()
    window.main_menu.card("tools").click()
    window.tools_screen.card("my_stats").click()
    assert window.library.scan().sessions[0].path != session.path


def test_files_outside_the_folder_cannot_be_deleted(
    window: MainWindow, tmp_path: Path
) -> None:
    browser = open_browser(window)
    browser.open_file(cash_session(tmp_path / "elsewhere.dat", hands=2))

    assert not browser.delete_button.isEnabled()
    assert "outside the session folder" in browser.delete_button.toolTip()


def test_the_session_of_a_game_being_played_cannot_be_deleted(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser = open_browser(window)
    session = browser.session
    assert session is not None
    monkeypatch.setattr(window, "paths_in_use", lambda: {session.path})
    browser.in_use = window.paths_in_use
    browser.show_session(session)

    assert not browser.delete_button.isEnabled()
    assert "still being played" in browser.delete_button.toolTip()


# --- Deleting all data --------------------------------------------------------------------


def test_delete_all_data(window: MainWindow, folder: Path, answers: list[bool]) -> None:
    window.save_setting("player_name", "Nael")
    window.profile.bankroll.set_balance(2_500)
    dialog = window.open_settings()

    answers.append(False)
    dialog.delete_all_button.click()
    assert len(list(folder.glob("*.dat"))) == 2

    dialog.delete_all_button.click()

    assert list(folder.glob("*.dat")) == []
    assert window.profile.bankroll.balance == DEFAULT_BALANCE
    assert window.profile.bankroll.transactions == []
    assert window.profile.settings.player_name == UserSettings().player_name
    assert dialog.name_edit.text() == UserSettings().player_name
    assert "100 000" in window.main_menu.bankroll_bar.balance_label.text()


def test_delete_all_data_waits_for_the_tables_to_close(
    window: MainWindow, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    told: list[str] = []
    monkeypatch.setattr(settings_dialog, "tell", lambda _p, _t, text: told.append(text))
    open_table(window, "cash")

    assert not window.delete_all_data()
    assert told and "Close your tables first" in told[0]
    assert len(list(folder.glob("*.dat"))) == 2


# --- Replay at the table ----------------------------------------------------------------


def test_a_table_replays_its_last_hand(
    window: MainWindow, process_until: ProcessUntil
) -> None:
    table = open_table(window, "cash")
    game = start_test_game(table, process_until)
    screen = table.table_screen
    assert not screen.replay_button.isEnabled()

    screen.action_panel.fold_button.click()
    process_until(lambda: screen.replay_button.isEnabled())

    screen.replay_button.click()
    replayer = table.replayer_window
    assert isinstance(replayer, ReplayerWindow) and replayer.isVisible()
    shown = replayer.replayer.replay
    assert shown is not None and shown.record.number == 1
    assert screen.game is game  # The table goes on.

    table.close()
    assert table.replayer_window is None
