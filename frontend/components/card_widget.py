"""A playing card painted with Qt, without image assets."""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from backend.poker_engine.constants import Card
from frontend import theme
from frontend.formatting import RANK_LABELS, SUIT_SYMBOLS

REVEAL_DURATION_MS = 250
TWO_COLORS = {
    "S": theme.CARD_BLACK,
    "H": theme.CARD_RED,
    "D": theme.CARD_RED,
    "C": theme.CARD_BLACK,
}
FOUR_COLORS = {
    "S": theme.CARD_BLACK,
    "H": theme.CARD_RED,
    "D": theme.CARD_BLUE,
    "C": theme.CARD_GREEN,
}
"""Every suit its own colour: diamonds and clubs never look like hearts and
spades."""


def suit_color(suit: str, four_colors: bool) -> QColor:
    return (FOUR_COLORS if four_colors else TWO_COLORS)[suit]


class CardWidget(QWidget):
    """Displays one card face up, face down, or an empty slot."""

    four_colors = False
    """The user's deck, for every card of the application (see ``suit_color``)."""

    def __init__(self, size: QSize, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size)

        self._card: Card | None = None
        self._face_up = False
        self._dimmed = False

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._reveal_animation = QPropertyAnimation(
            self._opacity_effect, b"opacity", self
        )
        self._reveal_animation.setDuration(REVEAL_DURATION_MS)
        self._reveal_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    @property
    def card(self) -> Card | None:
        return self._card

    @property
    def is_face_up(self) -> bool:
        return self._card is not None and self._face_up

    def set_card(
        self,
        card: Card | None,
        face_up: bool = True,
        dimmed: bool = False,
        animated: bool = False,
    ) -> None:
        """Show a card (or an empty slot when ``card`` is None)."""
        changed = (card, face_up) != (self._card, self._face_up)
        appeared = card is not None and changed

        self._card = card
        self._face_up = face_up
        self._dimmed = dimmed

        self._reveal_animation.stop()

        if animated and appeared:
            self._reveal_animation.setStartValue(0.0)
            self._reveal_animation.setEndValue(self._resting_opacity())
            self._reveal_animation.start()
        else:
            self._opacity_effect.setOpacity(self._resting_opacity())

        self.update()

    def _resting_opacity(self) -> float:
        return 0.45 if self._dimmed else 1.0

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = self.width() * 0.12

        if self._card is None:
            painter.setPen(QPen(QColor(255, 255, 255, 40), 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(0, 0, 0, 30))
            painter.drawRoundedRect(rect, radius, radius)
        elif self._face_up:
            self._paint_face(painter, rect, radius)
        else:
            self._paint_back(painter, rect, radius)

        painter.end()

    def _paint_face(self, painter: QPainter, rect: QRectF, radius: float) -> None:
        assert self._card is not None
        rank, suit = self._card[0], self._card[1]
        color = suit_color(suit, CardWidget.four_colors)

        painter.setPen(QPen(QColor("#b9bcc4"), 1))
        painter.setBrush(theme.CARD_FACE)
        painter.drawRoundedRect(rect, radius, radius)

        painter.setPen(color)

        rank_font = QFont(self.font())
        rank_font.setPixelSize(int(self.height() * 0.3))
        rank_font.setBold(True)
        painter.setFont(rank_font)
        painter.drawText(
            rect.adjusted(self.width() * 0.1, self.height() * 0.02, 0, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            RANK_LABELS.get(rank, rank),
        )

        suit_font = QFont(self.font())
        suit_font.setPixelSize(int(self.height() * 0.42))
        painter.setFont(suit_font)
        painter.drawText(
            rect.adjusted(0, self.height() * 0.3, 0, 0),
            Qt.AlignmentFlag.AlignCenter,
            SUIT_SYMBOLS[suit],
        )

    def _paint_back(self, painter: QPainter, rect: QRectF, radius: float) -> None:
        painter.setPen(QPen(QColor("#dfe6f2"), 1.5))
        painter.setBrush(theme.CARD_BACK)
        painter.drawRoundedRect(rect, radius, radius)

        inner = rect.adjusted(5, 5, -5, -5)
        painter.setPen(QPen(theme.CARD_BACK_PATTERN, 1.5))
        painter.setBrush(Qt.BrushStyle.DiagCrossPattern)
        painter.drawRoundedRect(inner, radius * 0.6, radius * 0.6)
