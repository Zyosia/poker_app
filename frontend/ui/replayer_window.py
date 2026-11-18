"""The hand replayer in a window of its own, opened from a table (V2.1).

The table goes on while you replay: the replayer shows the game's hands so
far, read from memory (``live_session_record``), and opens on the last one.
"""

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget

from backend.application.hand_records import SessionRecord

from .replayer_screen import ReplayerScreen

WINDOW_SIZE = (1100, 720)


def last_replayable_hand(session: SessionRecord) -> int | None:
    """The index of the last finished hand that can be replayed."""
    return next(
        (
            index
            for index in range(len(session.hands) - 1, -1, -1)
            if session.hands[index].finished and session.hands[index].replayable
        ),
        None,
    )


class ReplayerWindow(QWidget):
    """A replayer beside a table."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("guideWindow")  # The application's dark background.
        self.setWindowTitle(f"Replayer · {title}")
        self.resize(*WINDOW_SIZE)

        self.replayer = ReplayerScreen()
        self.replayer.back_button.setText("Close")
        self.replayer.back_requested.connect(self.close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.replayer)

    def show_hand(self, session: SessionRecord, index: int) -> None:
        self.replayer.show_hand(session, index)
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.replayer.stop()
        super().closeEvent(event)
