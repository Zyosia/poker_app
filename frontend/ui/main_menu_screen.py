"""First screen of the application: one card per game mode.

Once tables are open (each game plays in its own window), they are listed
below the cards, with the commands that arrange them.
"""

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from frontend.components.bankroll_bar import BankrollBar
from frontend.modes import Mode

CARD_COLUMNS = 3
TABLE_COLUMNS = 3
CARD_WIDTH = 250
CARD_HEIGHT = 156


class ModeCard(QPushButton):
    """A clickable card presenting a mode; disabled when not available yet."""

    def __init__(self, mode: Mode, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode = mode
        self.setObjectName("modeCard")
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setEnabled(mode.enabled)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if mode.enabled
            else Qt.CursorShape.ArrowCursor
        )
        self.setToolTip(mode.note or mode.description)

        symbol = QLabel(mode.symbol)
        symbol.setObjectName("modeSymbol")
        name = QLabel(mode.name)
        name.setObjectName("modeName")
        description = QLabel(mode.description)
        description.setObjectName("modeDescription")
        description.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(4)
        layout.addWidget(symbol)
        layout.addWidget(name)
        layout.addWidget(description)
        layout.addStretch()

        self.note_label = QLabel(mode.note or "")
        self.note_label.setObjectName("modeNote")
        self.note_label.setVisible(mode.note is not None)
        layout.addWidget(self.note_label)

        # The labels must not swallow the clicks meant for the card.
        for label in (symbol, name, description, self.note_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            label.setEnabled(mode.enabled)


class TablesPanel(QFrame):
    """The open tables: a click brings one to the front; Tile and Cascade
    arrange them all. The tables waiting for you are highlighted."""

    table_selected = Signal(int)
    """Emitted with the index of the table, in the order they opened."""
    tile_requested = Signal()
    cascade_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        title = QLabel("YOUR TABLES")
        title.setObjectName("sectionTitle")
        self.tile_button = QPushButton("Tile")
        self.tile_button.setObjectName("small")
        self.tile_button.setToolTip("Side by side, filling the screen.")
        self.tile_button.clicked.connect(self.tile_requested)
        self.cascade_button = QPushButton("Cascade")
        self.cascade_button.setObjectName("small")
        self.cascade_button.setToolTip("Stacked, each a little lower.")
        self.cascade_button.clicked.connect(self.cascade_requested)
        self.table_buttons: list[QPushButton] = []
        self._buttons_layout = QGridLayout()
        self._buttons_layout.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(title, stretch=1)
        header.addWidget(self.tile_button)
        header.addWidget(self.cascade_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 12)
        layout.addLayout(header)
        layout.addLayout(self._buttons_layout)
        self.hide()

    def show_tables(self, tables: Sequence[tuple[str, bool]]) -> None:
        """List the tables, each as (name, waiting for you)."""
        for button in self.table_buttons:
            button.hide()
            button.deleteLater()

        self.table_buttons = []

        for index, (name, waiting) in enumerate(tables):
            text = name.replace("&", "&&")  # Not a keyboard shortcut.
            button = QPushButton(f"● {text}" if waiting else text)
            button.setObjectName("tableButton")
            button.setProperty("yourTurn", waiting)
            button.setToolTip("Your turn: click to play." if waiting else "Show it.")
            button.clicked.connect(
                lambda _=False, index=index: self.table_selected.emit(index)
            )
            self._buttons_layout.addWidget(
                button, index // TABLE_COLUMNS, index % TABLE_COLUMNS
            )
            self.table_buttons.append(button)

        self.setVisible(bool(tables))


class MainMenuScreen(QWidget):
    """Lets the user pick a mode or quit."""

    mode_selected = Signal(object)
    """Emitted with the chosen ``Mode``."""
    quit_requested = Signal()
    guide_requested = Signal()

    def __init__(self, modes: Sequence[Mode], parent: QWidget | None = None) -> None:
        super().__init__(parent)

        title = QLabel("♠ ♥  POKER  ♦ ♣")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Texas Hold'em: No Limit, Pot Limit, Fixed Limit")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.cards: list[ModeCard] = []
        cards_panel = QWidget()
        grid = QGridLayout(cards_panel)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(18)

        for index, mode in enumerate(modes):
            card = ModeCard(mode)
            card.clicked.connect(lambda _=False, m=mode: self.mode_selected.emit(m))
            self.cards.append(card)
            grid.addWidget(card, index // CARD_COLUMNS, index % CARD_COLUMNS)

        self.guide_button = QPushButton("Guide")
        self.guide_button.setToolTip(
            "How the application works, the bot styles and the poker terms."
        )
        self.guide_button.setFixedWidth(200)
        self.guide_button.clicked.connect(self.guide_requested)
        self.quit_button = QPushButton("Quit")
        self.quit_button.setFixedWidth(200)
        self.quit_button.clicked.connect(self.quit_requested)
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addStretch()
        buttons.addWidget(self.guide_button)
        buttons.addWidget(self.quit_button)
        buttons.addStretch()

        self.bankroll_bar = BankrollBar()
        self.tables_panel = TablesPanel()
        self.tables_panel.setFixedWidth(CARD_COLUMNS * CARD_WIDTH + 2 * 18)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(self.bankroll_bar, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(30)
        layout.addWidget(cards_panel, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(18)
        layout.addWidget(self.tables_panel, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(18)
        layout.addLayout(buttons)
        layout.addStretch()

    def card(self, key: str) -> ModeCard:
        """Return the card of the mode registered under ``key``."""
        return next(card for card in self.cards if card.mode.key == key)
