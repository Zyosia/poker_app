"""Entry point of the desktop application.

Run with ``python -m frontend.main``.
"""

import multiprocessing
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from backend.application.profile import PROFILE_FILE_NAME, ProfileStore
from frontend.sounds import SoundPlayer
from frontend.theme import STYLESHEET
from frontend.ui.main_window import MainWindow


def profile_path() -> Path | None:
    """The user profile file, in the OS's application data folder."""
    folder = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )

    return Path(folder) / PROFILE_FILE_NAME if folder else None


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Poker")
    app.setStyleSheet(STYLESHEET)

    profile = ProfileStore(profile_path())
    window = MainWindow(profile=profile, sounds=SoundPlayer(audio=True))
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
