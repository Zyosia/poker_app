"""A small line chart drawn with QPainter: axes, zero line, legend and hover."""

import math
from collections.abc import Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

from frontend import theme

ChartPoint = tuple[int, tuple[int, ...]]
"""(x value, one y value per series)."""

LEFT_MARGIN = 78
RIGHT_MARGIN = 20
TOP_MARGIN = 40
BOTTOM_MARGIN = 40
TICK_COUNT = 5


def nice_step(span: float, ticks: int = TICK_COUNT) -> float:
    """Return a round tick step (1, 2 or 5 times a power of ten) for a span."""
    if span <= 0:
        return 1.0

    raw = span / ticks
    magnitude = 10 ** math.floor(math.log10(raw))

    for multiplier in (1, 2, 5, 10):
        if raw <= multiplier * magnitude:
            return multiplier * magnitude

    return 10 * magnitude


def format_value(value: float) -> str:
    """Format a value with thin separators and an explicit sign."""
    text = f"{abs(value):,.0f}".replace(",", " ")

    if value > 0:
        return f"+{text}"

    return f"−{text}" if value < 0 else "0"


class LineChart(QWidget):
    """Draws one line per series over a shared x axis."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(420, 260)
        self.setMouseTracking(True)

        self.x_label = "Hands"
        self.y_label = "Net chips"
        self.point_label = "Hand"
        """Names an x value in the hover text ("Hand 120")."""
        self.include_zero = True
        """Keep 0 on the y axis (net results); off for a balance."""
        self.signed_values = True
        """Show "+" before positive values (net results)."""
        self._names: tuple[str, ...] = ()
        self._points: list[ChartPoint] = []
        self._hover_index: int | None = None

    # --- Data ----------------------------------------------------------------

    def set_series(self, names: Sequence[str], points: Sequence[ChartPoint]) -> None:
        """Display new series; every point holds one value per name."""
        if any(len(values) != len(names) for _, values in points):
            raise ValueError("Every point needs one value per series.")

        self._names = tuple(names)
        self._points = list(points)
        self._hover_index = None
        self.update()

    @property
    def series_names(self) -> tuple[str, ...]:
        return self._names

    @property
    def points(self) -> list[ChartPoint]:
        return list(self._points)

    # --- Geometry ------------------------------------------------------------

    def plot_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(
            LEFT_MARGIN, TOP_MARGIN, -RIGHT_MARGIN, -BOTTOM_MARGIN
        )

    def _x_range(self) -> tuple[float, float]:
        if not self._points:
            return 0.0, 1.0

        first, last = self._points[0][0], self._points[-1][0]

        return float(first), float(max(last, first + 1))

    def _y_range(self) -> tuple[float, float, float]:
        """Return the rounded (low, high, step) of the y axis, zero included."""
        values = [value for _, point in self._points for value in point] or [0]

        if self.include_zero:
            low, high = min(0, *values), max(0, *values)
        else:
            low, high = min(values), max(values)

        step = nice_step(high - low or max(1.0, abs(high) / 10))

        if low == high:  # A flat line: centre it between two ticks.
            low, high = low - step, high + step

        return math.floor(low / step) * step, math.ceil(high / step) * step, step

    def _to_pixel(self, x: float, y: float) -> QPointF:
        plot = self.plot_rect()
        x_low, x_high = self._x_range()
        y_low, y_high, _ = self._y_range()
        x_ratio = (x - x_low) / (x_high - x_low)
        y_ratio = (y - y_low) / ((y_high - y_low) or 1.0)

        return QPointF(
            plot.left() + x_ratio * plot.width(),
            plot.bottom() - y_ratio * plot.height(),
        )

    def index_at(self, pixel_x: float) -> int | None:
        """Return the index of the point closest to a horizontal pixel."""
        if not self._points:
            return None

        return min(
            range(len(self._points)),
            key=lambda index: abs(
                self._to_pixel(self._points[index][0], 0).x() - pixel_x
            ),
        )

    def tooltip_text(self, index: int) -> str:
        """The hover text of a point: the hand number and every value."""
        x, values = self._points[index]
        lines = [f"{self.point_label} {x:,}".replace(",", " ")]
        ranked = sorted(
            zip(self._names, values, strict=True), key=lambda item: -item[1]
        )
        lines.extend(f"{name}: {self._format(value)}" for name, value in ranked)

        return "\n".join(lines)

    # --- Interaction ---------------------------------------------------------

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        position = event.position()
        inside = self.plot_rect().adjusted(-4, -4, 4, 4).contains(position)
        index = self.index_at(position.x()) if inside else None

        if index != self._hover_index:
            self._hover_index = index
            self.update()

        super().mouseMoveEvent(event)

    def leaveEvent(self, event: object) -> None:
        self._hover_index = None
        self.update()

    @property
    def hover_index(self) -> int | None:
        return self._hover_index

    # --- Painting ------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(self.font())
        font.setPixelSize(11)
        painter.setFont(font)

        self._paint_axes(painter)

        if self._points:
            self._paint_lines(painter)
            self._paint_legend(painter)

            if self._hover_index is not None:
                self._paint_hover(painter, self._hover_index)
        else:
            painter.setPen(theme.MUTED_TEXT)
            painter.drawText(self.plot_rect(), Qt.AlignmentFlag.AlignCenter, "No data")

        painter.end()

    def _paint_axes(self, painter: QPainter) -> None:
        plot = self.plot_rect()
        y_low, y_high, step = self._y_range()
        x_low, x_high = self._x_range()

        value = y_low
        while value <= y_high + step / 2:
            y = self._to_pixel(x_low, value).y()
            is_zero = abs(value) < step / 2
            painter.setPen(
                QPen(theme.MUTED_TEXT if is_zero else theme.GRID, 1.4 if is_zero else 1)
            )
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(theme.MUTED_TEXT)
            painter.drawText(
                QRectF(0, y - 8, LEFT_MARGIN - 8, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._format(value),
            )
            value += step

        x_step = max(1.0, nice_step(x_high - x_low))  # x values are whole.
        tick = math.ceil(x_low / x_step) * x_step

        while tick <= x_high:
            x = self._to_pixel(tick, y_low).x()
            painter.setPen(QPen(theme.GRID, 1))
            painter.drawLine(QPointF(x, plot.bottom()), QPointF(x, plot.bottom() + 4))
            painter.setPen(theme.MUTED_TEXT)
            painter.drawText(
                QRectF(x - 40, plot.bottom() + 6, 80, 16),
                Qt.AlignmentFlag.AlignHCenter,
                f"{tick:,.0f}".replace(",", " "),
            )
            tick += x_step

        painter.setPen(QPen(theme.GRID, 1))
        painter.drawLine(plot.bottomLeft(), plot.bottomRight())
        painter.drawLine(plot.bottomLeft(), plot.topLeft())

        painter.setPen(theme.MUTED_TEXT)
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 20, plot.width(), 18),
            Qt.AlignmentFlag.AlignHCenter,
            self.x_label,
        )
        painter.drawText(
            QRectF(4, 6, LEFT_MARGIN + 100, 18),
            Qt.AlignmentFlag.AlignLeft,
            self.y_label,
        )

    def _format(self, value: float) -> str:
        if self.signed_values:
            return format_value(value)

        return f"{value:,.0f}".replace(",", " ")

    def _series_color(self, index: int) -> QColor:
        return theme.SERIES_COLORS[index % len(theme.SERIES_COLORS)]

    def _paint_lines(self, painter: QPainter) -> None:
        for series in range(len(self._names)):
            path = QPainterPath()

            for index, (x, values) in enumerate(self._points):
                point = self._to_pixel(x, values[series])

                if index == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)

            painter.setPen(QPen(self._series_color(series), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

    def _paint_legend(self, painter: QPainter) -> None:
        x = self.plot_rect().left() + 110
        metrics = painter.fontMetrics()

        for series, name in enumerate(self._names):
            painter.setPen(QPen(self._series_color(series), 3))
            painter.drawLine(QPointF(x, 15), QPointF(x + 16, 15))
            painter.setPen(theme.TEXT)
            painter.drawText(QPointF(x + 22, 19), name)
            x += 22 + metrics.horizontalAdvance(name) + 18

    def _paint_hover(self, painter: QPainter, index: int) -> None:
        plot = self.plot_rect()
        x_value, values = self._points[index]
        x = self._to_pixel(x_value, 0).x()

        painter.setPen(QPen(theme.MUTED_TEXT, 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))

        for series, value in enumerate(values):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._series_color(series))
            painter.drawEllipse(self._to_pixel(x_value, value), 4, 4)

        lines = self.tooltip_text(index).split("\n")
        metrics = painter.fontMetrics()
        width = max(metrics.horizontalAdvance(line) for line in lines) + 20
        height = len(lines) * (metrics.height() + 2) + 12
        left = x + 12 if x + 12 + width < plot.right() else x - 12 - width
        box = QRectF(left, plot.top() + 6, width, height)

        painter.setPen(QPen(theme.GRID, 1))
        painter.setBrush(QColor(20, 24, 31, 235))
        painter.drawRoundedRect(box, 6, 6)
        painter.setPen(theme.TEXT)

        for line_index, line in enumerate(lines):
            painter.drawText(
                QPointF(
                    box.left() + 10,
                    box.top() + 6 + (line_index + 1) * (metrics.height() + 2) - 4,
                ),
                line,
            )
