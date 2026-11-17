"""The round ⚙ button opening the settings, with a gear painted by Qt."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPaintEvent, QTransform
from PySide6.QtWidgets import QPushButton, QWidget

from frontend import theme

GEAR_TEETH = 8


def gear_path(center: QPointF, radius: float) -> QPainterPath:
    """A gear of ``radius`` (to the tips of its teeth), with a hole."""
    body = QPainterPath()
    body.addEllipse(center, radius * 0.72, radius * 0.72)
    tooth_width = radius * 0.38

    for index in range(GEAR_TEETH):
        tooth = QPainterPath()
        tooth.addRoundedRect(
            QRectF(-tooth_width / 2, -radius, tooth_width, radius * 0.5),
            tooth_width * 0.2,
            tooth_width * 0.2,
        )
        rotation = QTransform().rotate(index * 360 / GEAR_TEETH)
        moved = QTransform.fromTranslate(center.x(), center.y())
        body = body.united((rotation * moved).map(tooth))

    hole = QPainterPath()
    hole.addEllipse(center, radius * 0.3, radius * 0.3)

    return body.subtracted(hole)


class SettingsButton(QPushButton):
    """Muted; gold when the mouse is over it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)  # The round background of the stylesheet.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.GOLD if self.underMouse() else theme.MUTED_TEXT)
        center = QRectF(self.rect()).center()
        painter.drawPath(gear_path(center, min(self.width(), self.height()) * 0.3))
        painter.end()
