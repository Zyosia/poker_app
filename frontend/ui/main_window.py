"""Main window: a stack of screens, starting with the main menu.

Opening a screen pushes it on the navigation stack; Back pops it, so Back
always returns to the previous screen.
"""

import random

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QWidget

from backend.application.controllers import HumanController
from backend.application.persistence import new_session_file_path
from backend.application.setup import (
    GameSettings,
    SpinSettings,
    TournamentSettings,
    create_game,
    create_spin_and_go,
    create_tournament,
)
from backend.application.tournament import Tournament
from backend.simulation.config import SimulationConfig
from backend.simulation.result import SimulationResult
from backend.simulation.tournament_runner import (
    TournamentRunConfig,
    TournamentRunResult,
)
from frontend.modes import MODES, Mode, ScreenKey

from .arena_progress_screen import ArenaProgressScreen
from .arena_results_screen import ArenaResultsScreen
from .arena_setup_screen import ArenaSetupScreen
from .arena_watch_screen import ArenaWatchScreen
from .cash_setup_screen import CashSetupScreen
from .game_screen import GameScreen
from .main_menu_screen import MainMenuScreen
from .tournament_results_screen import TournamentResultsScreen
from .tournament_screen import TournamentScreen
from .tournament_setup_screen import SpinSetupScreen, TournamentSetupScreen

PlayedSettings = TournamentSettings | SpinSettings


class MainWindow(QMainWindow):
    """Top-level window of the application."""

    def __init__(
        self,
        save_sessions: bool = True,
        parent: QWidget | None = None,
        rng: random.Random | None = None,
    ) -> None:
        """``rng`` draws the tournaments' cards and bots (seeded in tests)."""
        super().__init__(parent)
        self.setWindowTitle("Poker — No Limit Texas Hold'em")
        self.resize(1280, 800)
        self.setMinimumSize(1100, 700)

        self._save_sessions = save_sessions
        self._rng = rng or random.Random()

        self.main_menu = MainMenuScreen(MODES)
        self.cash_setup_screen = CashSetupScreen()
        self.game_screen = GameScreen()
        self.arena_setup_screen = ArenaSetupScreen()
        self.arena_progress_screen = ArenaProgressScreen()
        self.arena_results_screen = ArenaResultsScreen()
        self.arena_watch_screen = ArenaWatchScreen()
        self.tournament_setup_screen = TournamentSetupScreen()
        self.spin_setup_screen = SpinSetupScreen()
        self.tournament_screen = TournamentScreen()
        self.tournament_results_screen = TournamentResultsScreen()
        self._played_settings: PlayedSettings | None = None

        self.mode_screens: dict[ScreenKey, QWidget] = {
            ScreenKey.CASH_SETUP: self.cash_setup_screen,
            ScreenKey.ARENA_SETUP: self.arena_setup_screen,
            ScreenKey.TOURNAMENT_SETUP: self.tournament_setup_screen,
            ScreenKey.SPIN_SETUP: self.spin_setup_screen,
        }

        self.screens = QStackedWidget()

        for screen in (
            self.main_menu,
            self.cash_setup_screen,
            self.game_screen,
            self.arena_setup_screen,
            self.arena_progress_screen,
            self.arena_results_screen,
            self.arena_watch_screen,
            self.tournament_setup_screen,
            self.spin_setup_screen,
            self.tournament_screen,
            self.tournament_results_screen,
        ):
            self.screens.addWidget(screen)

        self.setCentralWidget(self.screens)
        self.history: list[QWidget] = [self.main_menu]

        self.main_menu.mode_selected.connect(self.open_mode)
        self.main_menu.quit_requested.connect(self.close)

        self.cash_setup_screen.start_requested.connect(self.start_game)
        self.cash_setup_screen.back_requested.connect(self.back)
        self.game_screen.menu_requested.connect(self.back)

        self.arena_setup_screen.run_requested.connect(self.run_arena)
        self.arena_setup_screen.watch_requested.connect(self.watch_arena)
        self.arena_setup_screen.back_requested.connect(self.back)
        self.arena_progress_screen.finished.connect(self.show_arena_result)
        self.arena_progress_screen.cancelled.connect(self.back)
        self.arena_results_screen.back_requested.connect(self.back)
        self.arena_results_screen.rerun_requested.connect(self.rerun_arena)
        self.arena_watch_screen.back_requested.connect(self.back)

        self.tournament_setup_screen.start_requested.connect(self.play_tournament)
        self.tournament_setup_screen.back_requested.connect(self.back)
        self.spin_setup_screen.start_requested.connect(self.play_tournament)
        self.spin_setup_screen.back_requested.connect(self.back)
        self.tournament_screen.menu_requested.connect(self.back_to_menu)
        self.tournament_screen.finished.connect(self.show_tournament_results)
        self.tournament_results_screen.play_again_requested.connect(self.play_again)
        self.tournament_results_screen.menu_requested.connect(self.back_to_menu)

    # --- Navigation ----------------------------------------------------------

    @property
    def current_screen(self) -> QWidget:
        return self.history[-1]

    def push(self, screen: QWidget) -> None:
        """Show a screen; Back returns to the current one."""
        self.history.append(screen)
        self.screens.setCurrentWidget(screen)

    def replace(self, screen: QWidget) -> None:
        """Show a screen in place of the current one."""
        self.history[-1] = screen
        self.screens.setCurrentWidget(screen)

    def back(self) -> None:
        """Return to the previous screen."""
        if len(self.history) == 1:
            return

        leaving = self.history.pop()

        self._stop(leaving)
        self.screens.setCurrentWidget(self.current_screen)

    def back_to_menu(self) -> None:
        """Leave whatever is shown and return to the main menu."""
        for screen in self.history[1:]:
            self._stop(screen)

        self.history = [self.main_menu]
        self.screens.setCurrentWidget(self.main_menu)

    def _stop(self, screen: QWidget) -> None:
        if screen is self.game_screen:
            self.game_screen.stop()
        elif screen is self.arena_watch_screen:
            self.arena_watch_screen.stop()
        elif screen is self.tournament_screen:
            self.tournament_screen.stop()

    def open_mode(self, mode: Mode) -> None:
        if mode.screen is not None:
            self.push(self.mode_screens[mode.screen])

    # --- Cash game -----------------------------------------------------------

    def start_game(self, settings: GameSettings) -> None:
        """Create a game from the settings and show the table."""
        game = create_game(
            settings=settings,
            human_controller=HumanController(),
            save_path=new_session_file_path() if self._save_sessions else None,
        )

        self.push(self.game_screen)
        self.game_screen.start_game(game, human_name=settings.player_name)

    # --- Tournament and Spin & Go ---------------------------------------------

    def play_tournament(self, settings: PlayedSettings) -> None:
        """Start a tournament or a Spin & Go and show its table."""
        self._played_settings = settings
        self.push(self.tournament_screen)
        self._start_played(settings)

    def play_again(self) -> None:
        if self._played_settings is not None:
            self.replace(self.tournament_screen)
            self._start_played(self._played_settings)

    def _start_played(self, settings: PlayedSettings) -> None:
        rng = random.Random(self._rng.getrandbits(64))

        if isinstance(settings, SpinSettings):
            tournament = create_spin_and_go(settings, HumanController(), rng)
        else:
            tournament = create_tournament(settings, HumanController(), rng)

        self.tournament_screen.start_tournament(
            tournament,
            human_name=settings.player_name,
            save_path=new_session_file_path() if self._save_sessions else None,
        )

    def show_tournament_results(self, tournament: Tournament) -> None:
        assert self._played_settings is not None
        self.tournament_results_screen.show_tournament(
            tournament, self._played_settings.player_name
        )
        self.replace(self.tournament_results_screen)

    # --- Bot Arena -----------------------------------------------------------

    def run_arena(self, config: SimulationConfig | TournamentRunConfig) -> None:
        self.push(self.arena_progress_screen)
        self.arena_progress_screen.start(config)

    def rerun_arena(self, config: SimulationConfig | TournamentRunConfig) -> None:
        self.replace(self.arena_progress_screen)
        self.arena_progress_screen.start(config)

    def show_arena_result(self, result: SimulationResult | TournamentRunResult) -> None:
        assert result.config.seed is not None
        self.arena_setup_screen.show_last_seed(result.config.seed)
        self.arena_results_screen.show_result(result)
        self.replace(self.arena_results_screen)

    def watch_arena(self, config: SimulationConfig) -> None:
        self.push(self.arena_watch_screen)
        self.arena_watch_screen.start(config)

    def closeEvent(self, event: QCloseEvent) -> None:
        # Never leave worker processes behind.
        self.arena_progress_screen.cancel()
        self.arena_progress_screen.wait()
        self.arena_watch_screen.stop()
        self.game_screen.stop()
        self.tournament_screen.stop()
        super().closeEvent(event)
