"""Main window: switches between the menu and the game."""

from PySide6.QtWidgets import QMainWindow, QStackedWidget, QWidget

from backend.application.controllers import HumanController
from backend.application.persistence import new_session_file_path
from backend.application.setup import GameSettings, create_game

from .game_screen import GameScreen
from .menu_screen import MenuScreen


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

        self.menu_screen = MenuScreen()
        self.game_screen = GameScreen()

        self.screens = QStackedWidget()
        self.screens.addWidget(self.menu_screen)
        self.screens.addWidget(self.game_screen)
        self.setCentralWidget(self.screens)

        self.menu_screen.start_requested.connect(self.start_game)
        self.menu_screen.quit_requested.connect(self.close)
        self.game_screen.menu_requested.connect(self.show_menu)

    def start_game(self, settings: GameSettings) -> None:
        """Create a game from the settings and show the table."""
        game = create_game(
            settings=settings,
            human_controller=HumanController(),
            save_path=new_session_file_path() if self._save_sessions else None,
        )

        self.screens.setCurrentWidget(self.game_screen)
        self.game_screen.start_game(game, human_name=settings.player_name)

    def show_menu(self) -> None:
        self.game_screen.stop()
        self.screens.setCurrentWidget(self.menu_screen)
