"""Fixtures for the PySide6 interface tests, run without a display."""

import os
from collections.abc import Callable

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

MAX_EVENT_LOOP_TURNS = 5000


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Return the application instance shared by every UI test."""
    existing = QApplication.instance()

    if isinstance(existing, QApplication):
        return existing

    return QApplication([])


@pytest.fixture
def process_until(qapp: QApplication) -> Callable[[Callable[[], bool]], None]:
    """Return a helper running the Qt event loop until a condition holds."""

    def run(condition: Callable[[], bool]) -> None:
        for _ in range(MAX_EVENT_LOOP_TURNS):
            if condition():
                return

            qapp.processEvents()

        raise AssertionError("The expected condition was never reached.")

    return run
