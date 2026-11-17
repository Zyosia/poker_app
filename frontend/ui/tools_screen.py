"""The Tools screen: one card per tool (V1.1)."""

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from frontend.modes import Mode

from .main_menu_screen import ModeCard

TOOL_COLUMNS = 2


class ToolsScreen(QWidget):
    """Lets the user pick a tool."""

    tool_selected = Signal(object)
    """Emitted with the chosen tool (a ``Mode``)."""
    back_requested = Signal()

    def __init__(self, tools: Sequence[Mode], parent: QWidget | None = None) -> None:
        super().__init__(parent)

        title = QLabel("TOOLS")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Study your games")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.cards: list[ModeCard] = []
        cards_panel = QWidget()
        grid = QGridLayout(cards_panel)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(18)

        for index, tool in enumerate(tools):
            card = ModeCard(tool)
            card.clicked.connect(lambda _=False, t=tool: self.tool_selected.emit(t))
            self.cards.append(card)
            grid.addWidget(card, index // TOOL_COLUMNS, index % TOOL_COLUMNS)

        self.message_label = QLabel()
        self.message_label.setObjectName("statusText")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.back_button = QPushButton("Back")
        self.back_button.setFixedWidth(200)
        self.back_button.clicked.connect(self.back_requested)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(30)
        layout.addWidget(cards_panel, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(12)
        layout.addWidget(self.message_label)
        layout.addSpacing(12)
        layout.addWidget(self.back_button, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

    def card(self, key: str) -> ModeCard:
        return next(card for card in self.cards if card.mode.key == key)
