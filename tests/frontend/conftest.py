"""Fixtures for the PySide6 interface tests, run without a display."""

import gc
import os
from collections.abc import Callable, Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from frontend.ui.arena_progress_screen import ArenaProgressScreen  # noqa: E402
from frontend.ui.arena_watch_screen import ArenaWatchScreen  # noqa: E402
from frontend.ui.equity_screen import EquityScreen  # noqa: E402
from frontend.ui.game_screen import GameScreen  # noqa: E402
from frontend.ui.replayer_screen import ReplayerScreen  # noqa: E402

MAX_EVENT_LOOP_TURNS = 5000


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Return the application instance shared by every UI test."""
    existing = QApplication.instance()

    if isinstance(existing, QApplication):
        return existing

    return QApplication([])


def tear_down(widget: QWidget) -> None:
    """Stop a screen's timers and background work before it is destroyed."""
    if isinstance(
        widget, GameScreen | ArenaWatchScreen | ReplayerScreen | EquityScreen
    ):
        widget.stop()
    elif isinstance(widget, ArenaProgressScreen):
        widget.cancel()
        widget.wait()


def destroy_top_level_widgets() -> None:
    """Destroy every window a test left behind, while the application exists.

    Screens created without a parent are often kept alive by reference
    cycles (slots that capture ``self``), so Python would only free them at
    interpreter exit, in no particular order with the ``QApplication``: a
    segmentation fault. Here each one is stopped, closed and deleted by Qt,
    and the pending deletions are processed at once.
    """
    for widget in QApplication.topLevelWidgets():
        if widget.parentWidget() is None:  # Not a combo box's own popup.
            tear_down(widget)
            widget.close()
            widget.deleteLater()

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.processEvents()
    gc.collect()


@pytest.fixture(autouse=True)
def clean_up_widgets(qapp: QApplication) -> Iterator[None]:
    """After each UI test: no window, timer or pending deletion survives."""
    yield
    destroy_top_level_widgets()


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
