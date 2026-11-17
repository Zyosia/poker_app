"""Helpers for the tests of the lobby and its game windows (multi-tabling)."""

from collections.abc import Callable

from backend.application.game import PokerGame
from frontend.ui.cash_setup_screen import CashSetupScreen
from frontend.ui.game_window import GameWindow
from frontend.ui.main_window import MainWindow
from frontend.ui.tournament_screen import TournamentScreen
from frontend.ui.tournament_setup_screen import SpinSetupScreen, TournamentSetupScreen
from tests.frontend.test_game_screen import HUMAN, make_game

ProcessUntil = Callable[[Callable[[], bool]], None]


def open_table(window: MainWindow, key: str) -> GameWindow:
    """Click a mode on the main menu: its game opens in a new window."""
    window.main_menu.card(key).click()
    table = window.game_windows[-1]
    table.table_screen.step_delay_ms = 0

    return table


def tournament_screen(table: GameWindow) -> TournamentScreen:
    screen = table.table_screen
    assert isinstance(screen, TournamentScreen)

    return screen


def start_test_game(table: GameWindow, process_until: ProcessUntil) -> PokerGame:
    """A table where Hero, the Button, acts first against passive bots."""
    game = make_game(dealer_index=0)
    table.push(table.table_screen)
    table.table_screen.start_game(game, human_name=HUMAN)
    process_until(lambda: game.is_waiting_for_human)

    return game


def cash_setup(table: GameWindow) -> CashSetupScreen:
    setup = table.setup_screen
    assert isinstance(setup, CashSetupScreen)

    return setup


def played_setup(table: GameWindow) -> TournamentSetupScreen | SpinSetupScreen:
    """The setup screen of a Tournament or a Spin & Go."""
    setup = table.setup_screen
    assert isinstance(setup, TournamentSetupScreen | SpinSetupScreen)

    return setup
