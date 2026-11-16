"""Entry point of the desktop application.

Run with ``python -m frontend.main``.
"""

import multiprocessing
import sys

from PySide6.QtWidgets import QApplication

from frontend.theme import STYLESHEET
from frontend.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Poker")
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    # The Bot Arena runs simulations in worker processes; this makes them
    # start correctly from a frozen (PyInstaller) build too.
    multiprocessing.freeze_support()
    sys.exit(main())
