"""A grouped bar chart drawn with QPainter: one group per category.

Used for the finishing-place distribution of tournament runs: one group per
place, one bar per bot, values between 0 and 1 shown as percentages.
"""

import math
from collections.abc import Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from frontend import theme

from .line_chart import BOTTOM_MARGIN, LEFT_MARGIN, RIGHT_MARGIN, TOP_MARGIN

GROUP_GAP = 0.25
"""Share of a group's width left empty between two groups."""


class BarChart(QWidget):
    """Draws ``values[series][category]`` as grouped bars."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(420, 260)
        self.setMouseTracking(True)

        self.y_label = "Share of finishes"
        self._categories: tuple[str, ...] = ()
        self._names: tuple[str, ...] = ()
        self._values: list[list[float]] = []
        self._hover_category: int | None = None

    def set_data(
        self,
        categories: Sequence[str],
        names: Sequence[str],
        values: Sequence[Sequence[float]],
    ) -> None:
        """``values`` holds one row per name, one value per category."""
        if len(values) != len(names) or any(
            len(row) != len(categories) for row in values
        ):
            raise ValueError("One row per series and one value per category.")

        self._categories = tuple(categories)
        self._names = tuple(names)
        self._values = [list(row) for row in values]
        self._hover_category = None
        self.update()

    @property
    def categories(self) -> tuple[str, ...]:
        return self._categories

    @property
    def series_names(self) -> tuple[str, ...]:
        return self._names

    @property
    def hover_category(self) -> int | None:
        return self._hover_category

    # --- Geometry ------------------------------------------------------------

    def plot_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(
            LEFT_MARGIN, TOP_MARGIN, -RIGHT_MARGIN, -BOTTOM_MARGIN
        )

    def _y_high(self) -> float:
        """Top of the axis: the next 10% above the highest bar."""
        highest = max((value for row in self._values for value in row), default=0)

        return max(0.1, math.ceil(highest * 10 - 1e-9) / 10)

    def group_rect(self, category: int) -> QRectF:
        plot = self.plot_rect()
        width = plot.width() / max(1, len(self._categories))

        return QRectF(plot.left() + category * width, plot.top(), width, plot.height())

    def bar_rect(self, series: int, category: int) -> QRectF:
        group = self.group_rect(category)
        inner = group.width() * (1 - GROUP_GAP)
        bar_width = inner / max(1, len(self._names))
        left = group.left() + group.width() * GROUP_GAP / 2 + series * bar_width
        height = group.height() * self._values[series][category] / self._y_high()

        return QRectF(left, group.bottom() - height, bar_width - 2, height)

    def category_at(self, pixel_x: float) -> int | None:
        for category in range(len(self._categories)):
            group = self.group_rect(category)

            if group.left() <= pixel_x < group.right():
                return category

        return None

    def tooltip_text(self, category: int) -> str:
        lines = [self._categories[category]]
        lines += [
            f"{name}: {row[category]:.1%}"
            for name, row in zip(self._names, self._values, strict=True)
        ]

        return "\n".join(lines)

    # --- Interaction ---------------------------------------------------------

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        position = event.position()
        inside = self.plot_rect().contains(position)
        category = self.category_at(position.x()) if inside else None

        if category != self._hover_category:
            self._hover_category = category
            self.update()

        super().mouseMoveEvent(event)

    def leaveEvent(self, event: object) -> None:
        self._hover_category = None
        self.update()

    # --- Painting ------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(self.font())
        font.setPixelSize(11)
        painter.setFont(font)

        self._paint_axes(painter)

        if self._categories and self._names:
            self._paint_bars(painter)
            self._paint_legend(painter)

            if self._hover_category is not None:
                self._paint_hover(painter, self._hover_category)
        else:
            painter.setPen(theme.MUTED_TEXT)
            painter.drawText(self.plot_rect(), Qt.AlignmentFlag.AlignCenter, "No data")

        painter.end()

    def _paint_axes(self, painter: QPainter) -> None:
        plot = self.plot_rect()
        high = self._y_high()
        step = 0.1 if high <= 0.5 else 0.2
        ticks = int(round(high / step))

        for tick in range(ticks + 1):
            value = tick * step
            y = plot.bottom() - plot.height() * value / high
            painter.setPen(QPen(theme.GRID, 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(theme.MUTED_TEXT)
            painter.drawText(
                QRectF(0, y - 8, LEFT_MARGIN - 8, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{value:.0%}",
            )

        for category, label in enumerate(self._categories):
            group = self.group_rect(category)
            painter.drawText(
                QRectF(group.left(), plot.bottom() + 6, group.width(), 16),
                Qt.AlignmentFlag.AlignHCenter,
                label,
            )

        painter.setPen(QPen(theme.GRID, 1))
        painter.drawLine(plot.bottomLeft(), plot.bottomRight())
        painter.setPen(theme.MUTED_TEXT)
        painter.drawText(
            QRectF(4, 6, LEFT_MARGIN + 140, 18),
            Qt.AlignmentFlag.AlignLeft,
            self.y_label,
        )

    def _color(self, series: int) -> QColor:
        return theme.SERIES_COLORS[series % len(theme.SERIES_COLORS)]

    def _paint_bars(self, painter: QPainter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)

        for series in range(len(self._names)):
            painter.setBrush(self._color(series))

            for category in range(len(self._categories)):
                painter.drawRect(self.bar_rect(series, category))

    def _paint_legend(self, painter: QPainter) -> None:
        x = self.plot_rect().left() + 150
        metrics = painter.fontMetrics()

        for series, name in enumerate(self._names):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._color(series))
            painter.drawRect(QRectF(x, 9, 12, 12))
            painter.setPen(theme.TEXT)
            painter.drawText(QPointF(x + 18, 19), name)
            x += 18 + metrics.horizontalAdvance(name) + 18

    def _paint_hover(self, painter: QPainter, category: int) -> None:
        group = self.group_rect(category)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 18))
        painter.drawRect(group)

        lines = self.tooltip_text(category).split("\n")
        metrics = painter.fontMetrics()
        width = max(metrics.horizontalAdvance(line) for line in lines) + 20
        height = len(lines) * (metrics.height() + 2) + 12
        plot = self.plot_rect()
        left = group.right() + 6
        left = left if left + width < plot.right() else group.left() - 6 - width
        box = QRectF(left, plot.top() + 6, width, height)

        painter.setPen(QPen(theme.GRID, 1))
        painter.setBrush(QColor(20, 24, 31, 235))
        painter.drawRoundedRect(box, 6, 6)
        painter.setPen(theme.TEXT)

        for index, line in enumerate(lines):
            painter.drawText(
                QPointF(
                    box.left() + 10,
                    box.top() + 2 + (index + 1) * (metrics.height() + 2),
                ),
                line,
            )
