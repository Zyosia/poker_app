"""Entry point of the desktop application.

Run with ``python -m frontend.main``.
"""

import multiprocessing
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from backend.application.persistence import SESSION_DIR
from backend.application.profile import PROFILE_FILE_NAME, ProfileStore
from frontend.sounds import SoundPlayer
from frontend.theme import STYLESHEET
from frontend.ui.main_window import MainWindow

APP_NAME = "Poker"
"""Run from the sources: the data folder of the development copy."""
BUILT_APP_NAME = "PokerApp"
"""A built application (PyInstaller) has a data folder of its own, so it
starts fresh for a new user and never shares the development copy's data."""
SESSIONS_FOLDER = "sessions"


def is_built() -> bool:
    """Run from a PyInstaller build rather than from the sources."""
    return bool(getattr(sys, "frozen", False))


def data_folder() -> Path | None:
    """The OS's application data folder, for the application name set."""
    folder = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )

    return Path(folder) if folder else None


def session_folder(folder: Path | None, built: bool) -> Path:
    """Where the sessions are saved. A build cannot keep them beside its code
    (a one-file build unpacks it to a temporary folder deleted at exit), so
    they go in its data folder; the sources keep ``backend/data/sessions``."""
    if built and folder is not None:
        return folder / SESSIONS_FOLDER

    return SESSION_DIR


def main() -> int:
    app = QApplication(sys.argv)
    built = is_built()
    app.setApplicationName(BUILT_APP_NAME if built else APP_NAME)
    app.setStyleSheet(STYLESHEET)

    folder = data_folder()
    profile = ProfileStore(folder / PROFILE_FILE_NAME if folder else None)
    window = MainWindow(
        session_dir=session_folder(folder, built),
        profile=profile,
        sounds=SoundPlayer(audio=True),
    )
    # Destroyed by Qt when closed, while the application still exists, rather
    # than by Python at exit in no particular order.
    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    window.show()

    if profile.warning is not None:
        QMessageBox.warning(window, "Profile", profile.warning)

    if window.startup_notice is not None:
        QMessageBox.information(window, "Bankroll", window.startup_notice)

    return app.exec()


if __name__ == "__main__":
    # The Bot Arena runs simulations in worker processes; this makes them
    # start correctly from a frozen (PyInstaller) build too.
    multiprocessing.freeze_support()
    sys.exit(main())
