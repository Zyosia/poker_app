"""Choosing cards with the mouse: card slots and a picker of the 52 cards."""

from collections.abc import Collection

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QGridLayout, QWidget

from backend.poker_engine.constants import RANKS, SUITS, Card
from frontend import theme

from .card_widget import CardWidget

PICKER_CARD_SIZE = QSize(34, 48)
PICKER_SUITS = "SHDC"
"""Rows of the picker: spades, hearts, diamonds, clubs."""


class CardSlot(CardWidget):
    """A place for one card: click to select it, right-click to empty it."""

    clicked = Signal()
    cleared = Signal()

    def __init__(self, size: QSize, parent: QWidget | None = None) -> None:
        super().__init__(size, parent)
        self.selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click, then pick a card. Right-click to empty.")

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.cleared.emit()
        else:
            self.clicked.emit()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)

        if self.selected:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(theme.GOLD, 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            radius = self.width() * 0.12
            painter.drawRoundedRect(
                QRectF(self.rect()).adjusted(2, 2, -2, -2), radius, radius
            )
            painter.end()


class PickableCard(CardWidget):
    """One card of the picker."""

    clicked = Signal(str)

    def __init__(self, card: Card, parent: QWidget | None = None) -> None:
        super().__init__(PICKER_CARD_SIZE, parent)
        self.set_card(card)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.card is not None:
            self.clicked.emit(self.card)


class CardPicker(QWidget):
    """The 52 cards, one row per suit; the cards already used are dimmed."""

    card_chosen = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cards: dict[Card, PickableCard] = {}
        self._used: set[Card] = set()
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        for row, suit in enumerate(PICKER_SUITS):
            for column, rank in enumerate(reversed(RANKS)):
                card = rank + suit
                widget = PickableCard(card)
                widget.clicked.connect(self._on_card_clicked)
                self.cards[card] = widget
                layout.addWidget(widget, row, column)

        assert set(PICKER_SUITS) == set(SUITS)

    def set_used(self, cards: Collection[Card]) -> None:
        self._used = set(cards)

        for card, widget in self.cards.items():
            widget.set_card(card, dimmed=card in self._used)

    def is_used(self, card: Card) -> bool:
        return card in self._used

    def _on_card_clicked(self, card: Card) -> None:
        if card not in self._used:
            self.card_chosen.emit(card)
