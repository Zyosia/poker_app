"""A window showing one screen at a time, with Back and the settings button.

Opening a screen pushes it on the navigation stack; Back pops it, so Back
always returns to the previous screen. The ⚙ button at the top left (or
Ctrl+,) asks for the settings, which open in their own small window.
"""

from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QSizePolicy, QStackedWidget, QWidget

from frontend import theme
from frontend.components.settings_button import SettingsButton

SETTINGS_SHORTCUT = "Ctrl+,"


class NavigationWindow(QMainWindow):
    """The lobby (``MainWindow``) and every game window (``GameWindow``)."""

    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.screens = QStackedWidget()
        self.screens.currentChanged.connect(self._size_to_current)
        self.setCentralWidget(self.screens)
        self.history: list[QWidget] = []

        # Above every screen; the tables leave room for it in their top bar.
        self.settings_button = SettingsButton(self)
        self.settings_button.setToolTip(f"Settings ({SETTINGS_SHORTCUT})")
        self.settings_button.setFixedSize(
            theme.SETTINGS_BUTTON_SIZE, theme.SETTINGS_BUTTON_SIZE
        )
        self.settings_button.move(
            theme.SETTINGS_BUTTON_MARGIN, theme.SETTINGS_BUTTON_MARGIN
        )
        self.settings_button.clicked.connect(self.settings_requested)
        QShortcut(QKeySequence(SETTINGS_SHORTCUT), self, self.settings_requested.emit)

    def add_screens(self, *screens: QWidget) -> None:
        for screen in screens:
            self.screens.addWidget(screen)

        self.settings_button.raise_()

    def _size_to_current(self) -> None:
        """Only the screen shown counts for the window's minimum size."""
        current = self.screens.currentWidget()
        ignored = QSizePolicy.Policy.Ignored
        preferred = QSizePolicy.Policy.Preferred

        for index in range(self.screens.count()):
            screen = self.screens.widget(index)
            policy = preferred if screen is current else ignored

            if screen is not None:
                screen.setSizePolicy(policy, policy)

    def show_first(self, screen: QWidget) -> None:
        """Start the navigation at ``screen``."""
        self.history = [screen]
        self.screens.setCurrentWidget(screen)
        self._size_to_current()  # Already current: no change signalled.

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

        self.stop_screen(self.history.pop())
        self.screens.setCurrentWidget(self.current_screen)
        self.refresh_bankroll()

    def back_to_first(self) -> None:
        """Leave whatever is shown and return to the first screen."""
        for screen in self.history[1:]:
            self.stop_screen(screen)

        self.show_first(self.history[0])
        self.refresh_bankroll()

    def stop_screen(self, screen: QWidget) -> None:
        """Stop what a screen left runs (a game, a replay...)."""

    def refresh_bankroll(self) -> None:
        """Show the current balance on the screens of this window."""
