"""One player seat: cards, name, stack and status."""

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from backend.poker_engine.constants import Card

from .card_widget import CardWidget

CARD_SIZE = QSize(46, 64)
SEAT_SIZE = QSize(150, 136)


class SeatHighlight(Enum):
    NONE = "none"
    ACTING = "acting"
    WINNER = "winner"


@dataclass(frozen=True)
class SeatState:
    """Everything a seat displays."""

    name: str
    stack: int
    cards: tuple[Card, ...]
    cards_face_up: bool
    status: str
    highlight: SeatHighlight = SeatHighlight.NONE
    dimmed: bool = False


BORDER_COLORS = {
    SeatHighlight.NONE: "#2c3442",
    SeatHighlight.ACTING: "#f2c14e",
    SeatHighlight.WINNER: "#3ddc84",
}


class SeatWidget(QFrame):
    """Displays a player around the table."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(SEAT_SIZE)

        self.card_widgets = [CardWidget(CARD_SIZE, self) for _ in range(2)]
        self.name_label = QLabel(self)
        self.stack_label = QLabel(self)
        self.status_label = QLabel(self)

        for label in (self.name_label, self.stack_label, self.status_label):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.name_label.setStyleSheet("font-weight: 700; font-size: 13px;")
        self.stack_label.setStyleSheet("color: #f2c14e; font-weight: 600;")
        self.status_label.setStyleSheet("color: #9aa4b2; font-size: 11px;")

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(4)
        cards_layout.addStretch()
        for card_widget in self.card_widgets:
            cards_layout.addWidget(card_widget)
        cards_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(1)
        layout.addLayout(cards_layout)
        layout.addWidget(self.name_label)
        layout.addWidget(self.stack_label)
        layout.addWidget(self.status_label)

        self._apply_highlight(SeatHighlight.NONE)

    def set_state(self, state: SeatState) -> None:
        """Update the seat from the given state."""
        self.name_label.setText(state.name)
        self.stack_label.setText(f"{state.stack:,}".replace(",", " "))
        self.status_label.setText(state.status)

        for index, card_widget in enumerate(self.card_widgets):
            card = state.cards[index] if index < len(state.cards) else None
            card_widget.set_card(card, face_up=state.cards_face_up, dimmed=state.dimmed)

        self._apply_highlight(state.highlight)

    def _apply_highlight(self, highlight: SeatHighlight) -> None:
        width = 1 if highlight == SeatHighlight.NONE else 2

        self.setStyleSheet(
            "SeatWidget {"
            " background-color: rgba(20, 24, 31, 215);"
            f" border: {width}px solid {BORDER_COLORS[highlight]};"
            " border-radius: 12px; }"
        )
