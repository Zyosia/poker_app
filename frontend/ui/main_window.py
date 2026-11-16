"""Main window: a stack of screens, starting with the main menu.

Opening a screen pushes it on the navigation stack; Back pops it, so Back
always returns to the previous screen.
"""

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QWidget

from backend.application.controllers import HumanController
from backend.application.persistence import new_session_file_path
from backend.application.setup import GameSettings, create_game
from backend.simulation.config import SimulationConfig
from backend.simulation.result import SimulationResult
from frontend.modes import MODES, Mode, ScreenKey

from .arena_progress_screen import ArenaProgressScreen
from .arena_results_screen import ArenaResultsScreen
from .arena_setup_screen import ArenaSetupScreen
from .arena_watch_screen import ArenaWatchScreen
from .cash_setup_screen import CashSetupScreen
from .game_screen import GameScreen
from .main_menu_screen import MainMenuScreen


class MainWindow(QMainWindow):
    """Top-level window of the application."""

    def __init__(
        self, save_sessions: bool = True, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Poker — No Limit Texas Hold'em")
        self.resize(1280, 800)
        self.setMinimumSize(1100, 700)

        self._save_sessions = save_sessions

        self.main_menu = MainMenuScreen(MODES)
        self.cash_setup_screen = CashSetupScreen()
        self.game_screen = GameScreen()
        self.arena_setup_screen = ArenaSetupScreen()
        self.arena_progress_screen = ArenaProgressScreen()
        self.arena_results_screen = ArenaResultsScreen()
        self.arena_watch_screen = ArenaWatchScreen()

        self.mode_screens: dict[ScreenKey, QWidget] = {
            ScreenKey.CASH_SETUP: self.cash_setup_screen,
            ScreenKey.ARENA_SETUP: self.arena_setup_screen,
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

        if leaving is self.game_screen:
            self.game_screen.stop()
        elif leaving is self.arena_watch_screen:
            self.arena_watch_screen.stop()

        self.screens.setCurrentWidget(self.current_screen)

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

    # --- Bot Arena -----------------------------------------------------------

    def run_arena(self, config: SimulationConfig) -> None:
        self.push(self.arena_progress_screen)
        self.arena_progress_screen.start(config)

    def rerun_arena(self, config: SimulationConfig) -> None:
        self.replace(self.arena_progress_screen)
        self.arena_progress_screen.start(config)

    def show_arena_result(self, result: SimulationResult) -> None:
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
        super().closeEvent(event)
