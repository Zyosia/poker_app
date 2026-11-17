"""First screen of the application: one card per game mode."""

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from frontend.formatting import format_chips
from frontend.modes import Mode

CARD_COLUMNS = 3
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


class MainMenuScreen(QWidget):
    """Lets the user pick a mode or quit."""

    mode_selected = Signal(object)
    """Emitted with the chosen ``Mode``."""
    quit_requested = Signal()
    bankroll_requested = Signal()
    reload_requested = Signal()

    def __init__(self, modes: Sequence[Mode], parent: QWidget | None = None) -> None:
        super().__init__(parent)

        title = QLabel("♠ ♥  POKER  ♦ ♣")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("No Limit Texas Hold'em")
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

        self.quit_button = QPushButton("Quit")
        self.quit_button.setFixedWidth(200)
        self.quit_button.clicked.connect(self.quit_requested)

        self.balance_label = QLabel()
        self.balance_label.setObjectName("statusText")
        self.bankroll_button = QPushButton("Bankroll")
        self.bankroll_button.setObjectName("small")
        self.bankroll_button.clicked.connect(self.bankroll_requested)
        self.reload_button = QPushButton("Reload")
        self.reload_button.setObjectName("accent")
        self.reload_button.setToolTip("Back to the default bankroll.")
        self.reload_button.clicked.connect(self.reload_requested)
        self.reload_button.hide()

        header = QHBoxLayout()
        header.addStretch()
        header.addWidget(self.balance_label)
        header.addWidget(self.reload_button)
        header.addWidget(self.bankroll_button)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(30)
        layout.addWidget(cards_panel, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(24)
        layout.addWidget(self.quit_button, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

    def set_balance(self, balance: int, can_reload: bool) -> None:
        """Show the bankroll, and the reload offer when nearly broke."""
        self.balance_label.setText(f"Bankroll  {format_chips(balance)}")
        self.reload_button.setVisible(can_reload)

    def card(self, key: str) -> ModeCard:
        """Return the card of the mode registered under ``key``."""
        return next(card for card in self.cards if card.mode.key == key)
