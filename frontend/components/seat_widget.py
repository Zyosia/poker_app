"""One player seat: cards, name, stack and status."""

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from backend.poker_engine.constants import Card
from frontend.formatting import format_amount

from .card_widget import CardWidget

CARD_SIZE = QSize(46, 64)
SEAT_SIZE = QSize(150, 136)
"""At full size: the table shrinks its seats in a small window (``set_scale``)."""
NAME_FONT_PX = 13
STATUS_FONT_PX = 11
STYLE_FONT_PX = 10
STACK_FONT_PX = 14
MIN_FONT_PX = 9
LINE_HEIGHT = 1.35
"""A text line, in font sizes."""


def scaled(size: QSize, scale: float) -> QSize:
    return QSize(round(size.width() * scale), round(size.height() * scale))


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
    big_blind: int | None = None
    """Show the stack in big blinds when set, in chips otherwise."""
    style: str = ""
    """The bot's play style, shown under its name ("": not shown)."""


BORDER_COLORS = {
    SeatHighlight.NONE: "#2c3442",
    SeatHighlight.ACTING: "#f2c14e",
    SeatHighlight.WINNER: "#3ddc84",
}


class SeatWidget(QFrame):
    """Displays a player around the table."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.scale = 1.0
        self.setFixedSize(SEAT_SIZE)

        self.card_widgets = [CardWidget(CARD_SIZE, self) for _ in range(2)]
        self.name_label = QLabel(self)
        self.style_label = QLabel(self)
        self.style_label.hide()
        self.stack_label = QLabel(self)
        self.status_label = QLabel(self)

        for label in (
            self.name_label,
            self.style_label,
            self.stack_label,
            self.status_label,
        ):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._style_labels()

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(4)
        cards_layout.addStretch()
        for card_widget in self.card_widgets:
            cards_layout.addWidget(card_widget)
        cards_layout.addStretch()

        layout = QVBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(1)
        layout.addLayout(cards_layout)
        layout.addWidget(self.name_label)
        layout.addWidget(self.style_label)
        layout.addWidget(self.stack_label)
        layout.addWidget(self.status_label)

        self._apply_highlight(SeatHighlight.NONE)

    def set_scale(self, scale: float) -> None:
        """Shrink (or restore) the seat: size, cards and text."""
        if scale == self.scale:
            return

        self.scale = scale
        card_size = scaled(CARD_SIZE, scale)
        margin = round(6 * scale)

        for card_widget in self.card_widgets:
            card_widget.setFixedSize(card_size)

        self._layout.setContentsMargins(margin + 2, margin, margin + 2, margin)
        self._style_labels()
        self._apply_size()

    def _apply_size(self) -> None:
        """Full size, or as tall as the content once shrunk; one line taller
        with the play style."""
        style_line = (
            round(self._font_px(STYLE_FONT_PX) * LINE_HEIGHT)
            if self.style_label.text()
            else 0
        )

        if self.scale == 1.0:
            self.setFixedSize(SEAT_SIZE.width(), SEAT_SIZE.height() + style_line)
            return

        # The text shrinks less than the cards (it stays readable): the seat
        # is as tall as its content.
        text = sum(
            round(self._font_px(size) * LINE_HEIGHT)
            for size in (NAME_FONT_PX, STACK_FONT_PX, STATUS_FONT_PX)
        )
        card_height = scaled(CARD_SIZE, self.scale).height()
        margin = round(6 * self.scale)
        height = card_height + text + style_line + 2 * margin + 4
        self.setFixedSize(round(SEAT_SIZE.width() * self.scale), height)

    def _font_px(self, size: int) -> int:
        return max(MIN_FONT_PX, round(size * self.scale))

    def _style_labels(self) -> None:
        self.name_label.setStyleSheet(
            f"font-weight: 700; font-size: {self._font_px(NAME_FONT_PX)}px;"
        )
        self.style_label.setStyleSheet(
            f"color: #8fb8ff; font-size: {self._font_px(STYLE_FONT_PX)}px;"
        )
        self.stack_label.setStyleSheet(
            "color: #f2c14e; font-weight: 600;"
            f" font-size: {self._font_px(STACK_FONT_PX)}px;"
        )
        self.status_label.setStyleSheet(
            f"color: #9aa4b2; font-size: {self._font_px(STATUS_FONT_PX)}px;"
        )

    def set_state(self, state: SeatState) -> None:
        """Update the seat from the given state."""
        self.name_label.setText(state.name)

        if state.style != self.style_label.text():
            self.style_label.setText(state.style)
            self.style_label.setVisible(bool(state.style))
            self._apply_size()

        self.stack_label.setText(format_amount(state.stack, state.big_blind))
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
