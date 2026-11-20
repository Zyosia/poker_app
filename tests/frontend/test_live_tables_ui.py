"""Live tables and watching them, and the game choice of the setups (V3.1.1)."""

import random
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from backend.application.profile import ProfileStore
from backend.poker_engine.constants import BettingRules, BettingStructure
from frontend.ui.arena_setup_screen import ArenaSetupScreen
from frontend.ui.main_window import MainWindow
from frontend.ui.tournament_screen import TournamentScreen
from tests.frontend.test_multi_table_ui import start_multi_table
from tests.frontend.windows import cash_setup, open_table, played_setup

TIMEOUT_SECONDS = 20
FIXED_LIMIT = BettingRules(BettingStructure.FIXED_LIMIT)


@pytest.fixture
def window(qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    window = MainWindow(
        save_sessions=False,
        rng=random.Random(15),
        profile=ProfileStore(tmp_path / "profile.json"),
    )
    yield window
    window.close()


def wait_for_your_turn(qapp: QApplication, screen: TournamentScreen) -> None:
    screen.step_delay_ms = 0
    deadline = time.monotonic() + TIMEOUT_SECONDS

    while not screen.tournament.is_waiting_for_human:
        assert time.monotonic() < deadline, "your turn never came"
        qapp.processEvents()


def play_others(screen: TournamentScreen, looks: int) -> None:
    """``looks`` looks at the other tables, each far enough in time that
    every table is due."""
    start = time.monotonic() + 3600

    for look in range(looks):
        screen.play_live_tables(now=start + 60 * look)


# --- Live tables ---------------------------------------------------------------


def test_the_other_tables_play_while_you_think(
    qapp: QApplication, window: MainWindow
) -> None:
    screen = start_multi_table(window)
    tournament = screen.tournament
    wait_for_your_turn(qapp, screen)

    assert tournament.live
    assert screen.is_playing_live_tables

    play_others(screen, looks=150)

    assert tournament.hands_played == 0  # Your first hand is not over.
    assert tournament.is_waiting_for_human
    assert sum(table.hands_played for table in tournament.tables[1:]) > 3


def test_pause_stops_the_other_tables(qapp: QApplication, window: MainWindow) -> None:
    screen = start_multi_table(window)
    wait_for_your_turn(qapp, screen)

    screen.toggle_pause()
    assert not screen.is_playing_live_tables

    screen.toggle_pause()
    assert screen.is_playing_live_tables


def test_your_table_says_when_it_waits_for_the_others(
    qapp: QApplication, window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    screen = start_multi_table(window)
    tournament = screen.tournament
    wait_for_your_turn(qapp, screen)
    screen.action_panel.fold_button.click()

    while tournament.is_hand_in_progress:
        qapp.processEvents()

    monkeypatch.setattr(tournament, "ready_to_deal", lambda: False)
    screen.continue_button.click()

    assert screen.is_waiting_for_tables
    assert "Waiting" in screen.outcome_label.text()
    assert not tournament.is_hand_in_progress

    monkeypatch.undo()
    play_others(screen, looks=1)

    assert not screen.is_waiting_for_tables
    assert tournament.is_hand_in_progress


# --- Watching another table ------------------------------------------------------


def test_another_table_is_watched_from_the_lobby(
    qapp: QApplication, window: MainWindow
) -> None:
    screen = start_multi_table(window)
    table_window = window.game_windows[-1]
    lobby = table_window.lobby_window
    assert lobby is not None
    lobby.right_tabs.setCurrentIndex(1)

    lobby.tables_table.selectRow(0)
    assert not lobby.watch_button.isEnabled()  # Your own table.

    lobby.tables_table.selectRow(1)
    assert lobby.watch_button.isEnabled()
    lobby.watch_button.click()

    spectator = table_window.spectator_windows[2]
    assert spectator.isVisible()
    assert spectator.info_label.text().startswith("TABLE 2")

    wait_for_your_turn(qapp, screen)
    play_others(screen, looks=40)

    watched = spectator.table
    assert watched is not None and watched.hands_played > 0
    assert "Hand #" in spectator.history_view.text()


def test_a_watched_table_that_breaks_says_so(
    qapp: QApplication, window: MainWindow
) -> None:
    screen = start_multi_table(window)
    table_window = window.game_windows[-1]
    spectator = table_window.watch_table(4)
    assert spectator is not None

    tournament = screen.tournament
    tournament.tables.remove(tournament.tables[3])  # As when table 4 breaks.
    spectator.refresh()

    assert "broke up" in spectator.info_label.text()


def test_closing_the_table_closes_the_windows_watching(window: MainWindow) -> None:
    start_multi_table(window)
    table_window = window.game_windows[-1]
    spectator = table_window.watch_table(2)
    assert spectator is not None

    table_window._close_spectators()  # noqa: SLF001 - also done on close

    assert table_window.spectator_windows == {}


# --- The game of every setup ------------------------------------------------------


def test_the_cash_game_setup_chooses_the_game(window: MainWindow) -> None:
    setup = cash_setup(open_table(window, "cash"))

    assert setup.current_settings().betting == BettingRules()

    setup.betting_picker.set_rules(FIXED_LIMIT)
    setup.betting_picker.changed.emit()

    assert setup.current_settings().betting == FIXED_LIMIT
    assert setup.subtitle.text() == "Fixed Limit Hold'em"

    setup.betting_picker.cap_spin.setValue(3)
    assert setup.current_settings().betting == BettingRules(
        BettingStructure.FIXED_LIMIT, 3
    )


def test_a_fixed_limit_table_shows_its_game(
    qapp: QApplication, window: MainWindow
) -> None:
    table = open_table(window, "cash")
    setup = cash_setup(table)
    setup.betting_picker.set_rules(FIXED_LIMIT)
    setup.play_button.click()

    assert "FL" in table.table_screen.info_label.text()
    game = table.table_screen.game
    assert game is not None and game.session.config.betting == FIXED_LIMIT


@pytest.mark.parametrize("mode", ["tournament", "spin"])
def test_the_tournament_setups_choose_the_game(window: MainWindow, mode: str) -> None:
    setup = played_setup(open_table(window, mode))
    pot_limit = BettingRules(BettingStructure.POT_LIMIT, 4)
    setup.betting_picker.set_rules(pot_limit)

    assert setup.current_settings().betting == pot_limit


def test_the_bot_arena_chooses_the_game(qapp: QApplication) -> None:
    setup = ArenaSetupScreen()
    setup.betting_picker.set_rules(FIXED_LIMIT)

    assert setup.current_config().betting == FIXED_LIMIT
