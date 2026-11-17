"""The poker table: felt, seats, community cards, bets and pot."""

import math
from dataclasses import dataclass
from functools import lru_cache

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
from .seat_widget import SeatState, SeatWidget, scaled

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
BET_FONT_PX = 13

FULL_SIZE = QSize(940, 600)
"""From this size on, the table is drawn at full scale."""
MIN_SCALE = 0.55
FULL_RING_SEATS = 7
FULL_RING_SCALE = 0.86
"""Seven to nine seats: smaller seats, so neighbours never overlap."""
MIN_SIZE = QSize(480, 240)
ARC_STEPS = 720
"""Steps measuring the rim, to space the seats evenly along it."""


def table_scale(width: int, height: int, seats: int) -> float:
    """How much the seats and cards shrink: in a small window (several
    tables side by side) and at a full-ring table."""
    scale = min(1.0, width / FULL_SIZE.width(), height / FULL_SIZE.height())

    if seats >= FULL_RING_SEATS:
        scale *= FULL_RING_SCALE

    return max(MIN_SCALE, scale)


@lru_cache(maxsize=64)
def seat_angles(count: int, radius_x: int, radius_y: int) -> tuple[float, ...]:
    """Where the seats sit on the rim (as angles), the first at the bottom.

    They are evenly spaced along the rim rather than by angle: on a wide
    table, the long sides get more seats than the ends, so a full ring
    leaves room between neighbours even when the table is short.
    """
    if count <= 0:
        return ()

    start = math.pi / 2
    angles = [start + 2 * math.pi * step / ARC_STEPS for step in range(ARC_STEPS + 1)]
    lengths = [0.0]

    for before, after in zip(angles, angles[1:], strict=False):
        lengths.append(
            lengths[-1]
            + math.hypot(
                radius_x * (math.cos(after) - math.cos(before)),
                radius_y * (math.sin(after) - math.sin(before)),
            )
        )

    perimeter = lengths[-1]
    seats = []
    step = 0

    for seat in range(count):
        target = perimeter * seat / count

        while lengths[step + 1] < target:
            step += 1

        span = lengths[step + 1] - lengths[step]
        share = (target - lengths[step]) / span if span else 0.0
        seats.append(angles[step] + share * (angles[step + 1] - angles[step]))

    return tuple(seats)


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
        self.setMinimumSize(MIN_SIZE)
        self.scale = 1.0

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
        horizontal = HORIZONTAL_MARGIN * self.scale

        return QRectF(self.rect()).adjusted(
            horizontal,
            TOP_MARGIN * self.scale,
            -horizontal,
            -BOTTOM_MARGIN * self.scale,
        )

    def _seat_center(self, seat_index: int) -> QPointF:
        """Return the center of a seat, the first seat being at the bottom."""
        table = self._table_rect()
        radius_x = table.width() / 2
        radius_y = table.height() / 2
        angles = seat_angles(len(self.seat_widgets), round(radius_x), round(radius_y))
        angle = angles[seat_index]

        return QPointF(
            table.center().x() + radius_x * math.cos(angle),
            table.center().y() + radius_y * math.sin(angle),
        )

    def _apply_scale(self) -> None:
        self.scale = table_scale(self.width(), self.height(), len(self.seat_widgets))
        card_size = scaled(BOARD_CARD_SIZE, self.scale)

        for seat_widget in self.seat_widgets:
            seat_widget.set_scale(self.scale)

        for card_widget in self.board_widgets:
            card_widget.setFixedSize(card_size)

    def _layout_children(self) -> None:
        self._apply_scale()
        center = self._table_rect().center()
        card_size = scaled(BOARD_CARD_SIZE, self.scale)
        spacing = BOARD_SPACING * self.scale

        for index, seat_widget in enumerate(self.seat_widgets):
            seat_center = self._seat_center(index)
            seat_widget.move(
                int(seat_center.x() - seat_widget.width() / 2),
                int(seat_center.y() - seat_widget.height() / 2),
            )

        board_width = (
            BOARD_CARD_COUNT * card_size.width() + (BOARD_CARD_COUNT - 1) * spacing
        )
        left = center.x() - board_width / 2
        top = center.y() - card_size.height() / 2 + 6 * self.scale

        for index, card_widget in enumerate(self.board_widgets):
            card_widget.move(
                int(left + index * (card_size.width() + spacing)), int(top)
            )

        self.pot_label.move(
            int(center.x() - self.pot_label.width() / 2),
            int(top - self.pot_label.height() - 12 * self.scale),
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
        font.setPixelSize(max(10, round(BET_FONT_PX * self.scale)))
        font.setBold(True)
        painter.setFont(font)

        chip = CHIP_RADIUS * max(0.75, self.scale)
        height = 24 * max(0.8, self.scale)
        text_width = painter.fontMetrics().horizontalAdvance(text)
        width = 2 * chip + text_width + 18
        pill = QRectF(
            position.x() - width / 2, position.y() - height / 2, width, height
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 120))
        painter.drawRoundedRect(pill, height / 2, height / 2)

        chip_center = QPointF(pill.left() + chip + 5, pill.center().y())
        painter.setPen(QPen(QColor("#ffffff"), 1.5, Qt.PenStyle.DashLine))
        painter.setBrush(theme.CHIP)
        painter.drawEllipse(chip_center, chip, chip)

        painter.setPen(theme.TEXT)
        painter.drawText(
            pill.adjusted(2 * chip + 10, 0, -6, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text,
        )

    def _paint_dealer_button(self, painter: QPainter, seat_index: int) -> None:
        center = self._table_rect().center()
        toward_seat = self._seat_center(seat_index) - center
        length = math.hypot(toward_seat.x(), toward_seat.y()) or 1.0

        # Shift the button sideways so it does not overlap the bet.
        sideways = QPointF(-toward_seat.y() / length, toward_seat.x() / length) * (
            52 * self.scale
        )
        position = (
            self._point_toward_center(seat_index, DEALER_DISTANCE_RATIO) + sideways
        )
        radius = DEALER_BUTTON_RADIUS * max(0.8, self.scale)

        painter.setPen(QPen(QColor("#8a8a8a"), 1.5))
        painter.setBrush(QColor("#f7f7f2"))
        painter.drawEllipse(position, radius, radius)

        font = QFont(self.font())
        font.setPixelSize(max(9, round(12 * self.scale)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(theme.CARD_BLACK)
        painter.drawText(
            QRectF(
                position.x() - radius, position.y() - radius, 2 * radius, 2 * radius
            ),
            Qt.AlignmentFlag.AlignCenter,
            "D",
        )
