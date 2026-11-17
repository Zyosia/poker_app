"""The 13 × 13 grid of starting hands, painted with the mouse."""

from collections.abc import Collection

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from backend.application.ranges import grid_label

CELLS = 13
MIN_CELL = 26
SELECTED = {"pair": QColor("#d9a530"), "s": QColor("#2f8f5b"), "o": QColor("#3f6fb8")}
EMPTY = QColor("#232a36")


def cell_kind(label: str) -> str:
    return "pair" if len(label) == 2 else label[2]


class RangeGrid(QWidget):
    """Pairs on the diagonal, suited hands above it, offsuit below.

    A click selects or removes a hand; dragging paints the same way over
    every cell the mouse goes over.
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(CELLS * MIN_CELL, CELLS * MIN_CELL)
        self.setMouseTracking(False)
        self._labels: set[str] = set()
        self._painting: bool | None = None
        """While dragging: True adds hands, False removes them."""

    def labels(self) -> frozenset[str]:
        return frozenset(self._labels)

    def set_labels(self, labels: Collection[str]) -> None:
        """Show a range, without emitting ``changed``."""
        self._labels = set(labels)
        self.update()

    def toggle(self, label: str) -> None:
        self._labels ^= {label}
        self.update()
        self.changed.emit()

    # --- Geometry ------------------------------------------------------------

    def _cell_size(self) -> float:
        return min(self.width(), self.height()) / CELLS

    def cell_rect(self, label: str) -> QRectF:
        size = self._cell_size()

        for row in range(CELLS):
            for column in range(CELLS):
                if grid_label(row, column) == label:
                    return QRectF(column * size, row * size, size, size)

        raise ValueError(f"No cell for {label}.")

    def label_at(self, point: QPointF) -> str | None:
        size = self._cell_size()
        row, column = int(point.y() // size), int(point.x() // size)

        if 0 <= row < CELLS and 0 <= column < CELLS:
            return grid_label(row, column)

        return None

    # --- Mouse ---------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        label = self.label_at(event.position())

        if label is not None:
            self._painting = label not in self._labels
            self._paint(label)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        label = self.label_at(event.position())

        if label is not None and self._painting is not None:
            self._paint(label)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._painting = None

    def _paint(self, label: str) -> None:
        if (label in self._labels) == self._painting:
            return

        if self._painting:
            self._labels.add(label)
        else:
            self._labels.discard(label)

        self.update()
        self.changed.emit()

    # --- Painting ------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        size = self._cell_size()
        font = QFont(self.font())
        font.setPixelSize(max(9, int(size * 0.36)))
        font.setBold(True)
        painter.setFont(font)

        for row in range(CELLS):
            for column in range(CELLS):
                label = grid_label(row, column)
                rect = QRectF(column * size, row * size, size, size).adjusted(
                    1, 1, -1, -1
                )
                selected = label in self._labels
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(SELECTED[cell_kind(label)] if selected else EMPTY)
                painter.drawRoundedRect(rect, 3, 3)
                painter.setPen(QPen(QColor("#ffffff" if selected else "#7d8796")))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

        painter.end()
