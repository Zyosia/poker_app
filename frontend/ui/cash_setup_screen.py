"""Configuration of a cash game against bots."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from backend.application.action_clock import CASH_CLOCK
from backend.application.bankroll import DEFAULT_BALANCE, GameMode
from backend.application.setup import BotLevel, GameSettings
from backend.poker_engine.constants import MAX_TABLE_SEATS
from frontend.components.bankroll_bar import BankrollBar
from frontend.components.buy_in_info import BuyInInfo
from frontend.components.clock_combo import ClockCombo

BLIND_LEVELS = ((5, 10), (10, 20), (25, 50), (50, 100))
BOT_LEVEL_LABELS = {
    BotLevel.NORMAL: "Normal — plays its hand strength",
    BotLevel.EASY: "Easy — plays randomly",
}
DEFAULT_SETTINGS = GameSettings()


def player_name_label(name: str) -> QLabel:
    """Your name, as chosen in the settings."""
    label = QLabel(name)
    label.setObjectName("playerName")
    label.setToolTip("Change your name in the settings (⚙, top left).")

    return label


class CashSetupScreen(QWidget):
    """Lets the user configure and start a cash game."""

    start_requested = Signal(GameSettings)
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        title = QLabel("♠  CASH GAME")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("No Limit Texas Hold'em")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.bankroll_bar = BankrollBar()
        self.name_label = player_name_label(DEFAULT_SETTINGS.player_name)

        self.opponents_spin = QSpinBox()
        self.opponents_spin.setRange(1, MAX_TABLE_SEATS - 1)
        self.opponents_spin.setValue(DEFAULT_SETTINGS.opponent_count)

        self.level_combo = QComboBox()
        for level, label in BOT_LEVEL_LABELS.items():
            self.level_combo.addItem(label, level)

        self.stack_spin = QSpinBox()
        self.stack_spin.setRange(200, 100_000)
        self.stack_spin.setSingleStep(100)
        self.stack_spin.setValue(DEFAULT_SETTINGS.starting_stack)

        self.blinds_combo = QComboBox()
        for small_blind, big_blind in BLIND_LEVELS:
            self.blinds_combo.addItem(
                f"{small_blind} / {big_blind}", (small_blind, big_blind)
            )

        self.clock_combo = ClockCombo(CASH_CLOCK)
        self.buy_in_info = BuyInInfo(GameMode.CASH)
        self._balance = DEFAULT_BALANCE
        self._hints = True
        self.stack_spin.valueChanged.connect(self.refresh_cost)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #ff7b7b;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.play_button = QPushButton("Play")
        self.play_button.setObjectName("primary")
        self.play_button.setMinimumHeight(46)
        self.play_button.clicked.connect(self._on_play_clicked)
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.back_requested)

        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(18)
        form.addRow("Your name", self.name_label)
        form.addRow("Opponents", self.opponents_spin)
        form.addRow("Bot level", self.level_combo)
        form.addRow("Starting stack", self.stack_spin)
        form.addRow("Blinds", self.blinds_combo)
        form.addRow("Action clock", self.clock_combo)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(460)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(28, 26, 28, 26)
        panel_layout.setSpacing(16)
        panel_layout.addLayout(form)
        panel_layout.addWidget(self.buy_in_info)
        panel_layout.addWidget(self.error_label)
        panel_layout.addWidget(self.play_button)
        panel_layout.addWidget(self.back_button)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(self.bankroll_bar, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(24)
        layout.addWidget(panel, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

    def cost(self) -> int:
        """The buy-in: the starting stack, paid from the bankroll."""
        return self.stack_spin.value()

    def set_bankroll(self, balance: int, hints: bool) -> None:
        self._balance = balance
        self._hints = hints
        self.refresh_cost()

    def set_player_name(self, name: str) -> None:
        self.name_label.setText(name)

    def refresh_cost(self) -> None:
        affordable = self.buy_in_info.refresh(self.cost(), self._balance, self._hints)
        self.play_button.setEnabled(affordable)

    def current_settings(self) -> GameSettings:
        """Return the settings currently entered in the form."""
        small_blind, big_blind = self.blinds_combo.currentData()

        return GameSettings(
            player_name=self.name_label.text(),
            opponent_count=self.opponents_spin.value(),
            bot_level=self.level_combo.currentData(),
            starting_stack=self.stack_spin.value(),
            small_blind=small_blind,
            big_blind=big_blind,
        )

    def _on_play_clicked(self) -> None:
        try:
            settings = self.current_settings()
        except ValueError as error:
            self.error_label.setText(str(error))
            return

        self.error_label.clear()
        self.start_requested.emit(settings)
