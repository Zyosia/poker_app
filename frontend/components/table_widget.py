"""The poker table: felt, seats, community cards, bets and pot."""

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPaintEvent,
    QPen,
    QRadialGradient,
    QResizeEvent,
)
from PySide6.QtWidgets import QLabel, QWidget

from backend.poker_engine.constants import Card
from frontend import theme
from frontend.formatting import format_amount

from .card_widget import CardWidget
from .seat_widget import SEAT_SIZE, SeatState, SeatWidget

BOARD_CARD_SIZE = QSize(62, 88)
BOARD_CARD_COUNT = 5
BOARD_SPACING = 8
HORIZONTAL_MARGIN = 96
TOP_MARGIN = 74
BOTTOM_MARGIN = 84
RIM_WIDTH = 16
BET_DISTANCE_RATIO = 0.58
DEALER_DISTANCE_RATIO = 0.54
DEALER_BUTTON_RADIUS = 11
CHIP_RADIUS = 8


@dataclass(frozen=True)
class TableState:
    """Everything the table displays.

    Seats are listed clockwise; the first one is drawn at the bottom of the
    table. ``bets`` holds the chips each seat has in front of it. Amounts
    are shown in big blinds when ``big_blind`` is set, in chips otherwise.
    """

    seats: tuple[SeatState, ...]
    bets: tuple[int, ...]
    dealer_seat: int | None
    community_cards: tuple[Card, ...]
    pot: int
    big_blind: int | None = None


class TableWidget(QWidget):
    """Draws the table and lays the seats out around it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(760, 480)

        self._state = TableState(
            seats=(), bets=(), dealer_seat=None, community_cards=(), pot=0
        )
        self.seat_widgets: list[SeatWidget] = []
        self.board_widgets = [
            CardWidget(BOARD_CARD_SIZE, self) for _ in range(BOARD_CARD_COUNT)
        ]

        self.pot_label = QLabel(self)
        self.pot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pot_label.setStyleSheet(
            "background-color: rgba(0, 0, 0, 110); color: #f2c14e;"
            " font-size: 16px; font-weight: 700;"
            " border-radius: 13px; padding: 3px 14px;"
        )

    def set_state(self, state: TableState) -> None:
        """Display a new table state."""
        if len(state.seats) != len(self.seat_widgets):
            self._rebuild_seats(len(state.seats))

        self._state = state

        for seat_widget, seat_state in zip(self.seat_widgets, state.seats, strict=True):
            seat_widget.set_state(seat_state)

        for index, card_widget in enumerate(self.board_widgets):
            card = (
                state.community_cards[index]
                if index < len(state.community_cards)
                else None
            )
            card_widget.set_card(card, face_up=True, animated=True)

        self.pot_label.setText(f"Pot  {format_amount(state.pot, state.big_blind)}")
        self.pot_label.setVisible(state.pot > 0)
        self.pot_label.adjustSize()

        self._layout_children()
        self.update()

    @property
    def state(self) -> TableState:
        """The state displayed."""
        return self._state

    def bet_texts(self) -> list[str]:
        """The labels drawn for the bets in front of the seats (seat order)."""
        return [
            format_amount(bet, self._state.big_blind)
            for bet in self._state.bets
            if bet > 0
        ]

    def _rebuild_seats(self, count: int) -> None:
        for seat_widget in self.seat_widgets:
            seat_widget.hide()  # At once: deleteLater waits for the event loop.
            seat_widget.deleteLater()

        self.seat_widgets = [SeatWidget(self) for _ in range(count)]

        for seat_widget in self.seat_widgets:
            seat_widget.show()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._layout_children()

    def _table_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(
            HORIZONTAL_MARGIN, TOP_MARGIN, -HORIZONTAL_MARGIN, -BOTTOM_MARGIN
        )

    def _seat_center(self, seat_index: int) -> QPointF:
        """Return the center of a seat, the first seat being at the bottom."""
        table = self._table_rect()
        angle = math.pi / 2 + seat_index * 2 * math.pi / max(1, len(self.seat_widgets))

        return QPointF(
            table.center().x() + table.width() / 2 * math.cos(angle),
            table.center().y() + table.height() / 2 * math.sin(angle),
        )

    def _layout_children(self) -> None:
        center = self._table_rect().center()

        for index, seat_widget in enumerate(self.seat_widgets):
            seat_center = self._seat_center(index)
            seat_widget.move(
                int(seat_center.x() - SEAT_SIZE.width() / 2),
                int(seat_center.y() - SEAT_SIZE.height() / 2),
            )

        board_width = (
            BOARD_CARD_COUNT * BOARD_CARD_SIZE.width()
            + (BOARD_CARD_COUNT - 1) * BOARD_SPACING
        )
        left = center.x() - board_width / 2
        top = center.y() - BOARD_CARD_SIZE.height() / 2 + 6

        for index, card_widget in enumerate(self.board_widgets):
            card_widget.move(
                int(left + index * (BOARD_CARD_SIZE.width() + BOARD_SPACING)),
                int(top),
            )

        self.pot_label.move(
            int(center.x() - self.pot_label.width() / 2),
            int(top - self.pot_label.height() - 12),
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._paint_felt(painter)

        for index, bet in enumerate(self._state.bets):
            if bet > 0:
                self._paint_bet(painter, index, bet)

        if self._state.dealer_seat is not None:
            self._paint_dealer_button(painter, self._state.dealer_seat)

        painter.end()

    def _paint_felt(self, painter: QPainter) -> None:
        table = self._table_rect()

        painter.setPen(QPen(theme.TABLE_RIM_LIGHT, 2))
        painter.setBrush(theme.TABLE_RIM)
        painter.drawEllipse(table)

        felt = table.adjusted(RIM_WIDTH, RIM_WIDTH, -RIM_WIDTH, -RIM_WIDTH)
        gradient = QRadialGradient(felt.center(), felt.width() / 2)
        gradient.setColorAt(0.0, theme.FELT_CENTER)
        gradient.setColorAt(1.0, theme.FELT_EDGE)

        painter.setPen(QPen(QColor(0, 0, 0, 90), 2))
        painter.setBrush(gradient)
        painter.drawEllipse(felt)

        painter.setPen(QPen(QColor(255, 255, 255, 28), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(felt.adjusted(26, 26, -26, -26))

    def _point_toward_center(self, seat_index: int, ratio: float) -> QPointF:
        """Return the point at ``ratio`` of the way from the center to a seat."""
        center = self._table_rect().center()
        seat_center = self._seat_center(seat_index)

        return center + (seat_center - center) * ratio

    def _paint_bet(self, painter: QPainter, seat_index: int, bet: int) -> None:
        position = self._point_toward_center(seat_index, BET_DISTANCE_RATIO)
        text = format_amount(bet, self._state.big_blind)

        font = QFont(self.font())
        font.setPixelSize(13)
        font.setBold(True)
        painter.setFont(font)

        text_width = painter.fontMetrics().horizontalAdvance(text)
        width = 2 * CHIP_RADIUS + text_width + 18
        pill = QRectF(position.x() - width / 2, position.y() - 12, width, 24)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 120))
        painter.drawRoundedRect(pill, 12, 12)

        chip_center = QPointF(pill.left() + CHIP_RADIUS + 5, pill.center().y())
        painter.setPen(QPen(QColor("#ffffff"), 1.5, Qt.PenStyle.DashLine))
        painter.setBrush(theme.CHIP)
        painter.drawEllipse(chip_center, CHIP_RADIUS, CHIP_RADIUS)

        painter.setPen(theme.TEXT)
        painter.drawText(
            pill.adjusted(2 * CHIP_RADIUS + 10, 0, -6, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text,
        )

    def _paint_dealer_button(self, painter: QPainter, seat_index: int) -> None:
        center = self._table_rect().center()
        toward_seat = self._seat_center(seat_index) - center
        length = math.hypot(toward_seat.x(), toward_seat.y()) or 1.0

        # Shift the button sideways so it does not overlap the bet.
        sideways = QPointF(-toward_seat.y() / length, toward_seat.x() / length) * 52
        position = (
            self._point_toward_center(seat_index, DEALER_DISTANCE_RATIO) + sideways
        )

        painter.setPen(QPen(QColor("#8a8a8a"), 1.5))
        painter.setBrush(QColor("#f7f7f2"))
        painter.drawEllipse(position, DEALER_BUTTON_RADIUS, DEALER_BUTTON_RADIUS)

        font = QFont(self.font())
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(theme.CARD_BLACK)
        painter.drawText(
            QRectF(
                position.x() - DEALER_BUTTON_RADIUS,
                position.y() - DEALER_BUTTON_RADIUS,
                2 * DEALER_BUTTON_RADIUS,
                2 * DEALER_BUTTON_RADIUS,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "D",
        )
