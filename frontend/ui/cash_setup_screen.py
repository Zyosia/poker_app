"""Configuration of a cash game against bots."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from backend.application.action_clock import CASH_CLOCK
from backend.application.bankroll import DEFAULT_BALANCE, GameMode
from backend.application.cash_rules import (
    MAX_BUY_IN_BIG_BLINDS,
    MIN_BUY_IN_BIG_BLINDS,
    BuyInRange,
)
from backend.application.game_modes import game_name
from backend.application.setup import GameSettings
from backend.poker_engine.constants import NO_LIMIT
from frontend.components.bankroll_bar import BankrollBar
from frontend.components.betting_picker import BettingPicker
from frontend.components.bot_picker import BotPicker
from frontend.components.buy_in_info import BuyInInfo
from frontend.components.clock_combo import ClockCombo

BLIND_LEVELS = ((5, 10), (10, 20), (25, 50), (50, 100))
DEFAULT_SETTINGS = GameSettings()


def player_name_label(name: str) -> QLabel:
    """Your name, as chosen in the settings."""
    label = QLabel(name)
    label.setObjectName("playerName")
    label.setToolTip("Change your name in the settings (⚙, top left).")

    return label


def scrolling(content: QLayout) -> QVBoxLayout:
    """A setup page that scrolls in a small window rather than being squeezed
    (several tables side by side)."""
    page = QWidget()
    page.setLayout(content)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(page)
    area.viewport().setAutoFillBackground(False)
    page.setAutoFillBackground(False)

    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(area)

    return layout


class CashSetupScreen(QWidget):
    """Lets the user configure and start a cash game."""

    start_requested = Signal(GameSettings)
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        title = QLabel("♠  CASH GAME")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel(game_name(NO_LIMIT))
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle = subtitle
        self.betting_picker = BettingPicker()
        self.betting_picker.changed.connect(
            lambda: subtitle.setText(game_name(self.betting_picker.rules()))
        )

        self.bankroll_bar = BankrollBar()
        self.name_label = player_name_label(DEFAULT_SETTINGS.player_name)

        self.bot_picker = BotPicker(DEFAULT_SETTINGS.opponents)
        self.opponents_spin = self.bot_picker.opponents_spin
        self.same_style_check = self.bot_picker.same_style_check
        self.bot_combos = self.bot_picker.bot_combos

        self.stack_spin = QSpinBox()
        self.stack_spin.setToolTip(
            f"A seat is bought for {MIN_BUY_IN_BIG_BLINDS} to "
            f"{MAX_BUY_IN_BIG_BLINDS} big blinds; rebuys and top-ups too."
        )

        self.blinds_combo = QComboBox()
        for small_blind, big_blind in BLIND_LEVELS:
            self.blinds_combo.addItem(
                f"{small_blind} / {big_blind}", (small_blind, big_blind)
            )

        self._big_blind = DEFAULT_SETTINGS.big_blind
        self._apply_buy_in_range(DEFAULT_SETTINGS.starting_stack)
        self.blinds_combo.currentIndexChanged.connect(self._on_blinds_changed)

        self.straddle_check = QCheckBox("Straddle: under the gun posts 2 BB")
        self.straddle_check.setToolTip(
            "Every hand, the player under the gun posts a straddle of two big "
            "blinds and acts last before the flop (three players or more)."
        )
        self.bots_rebuy_check = QCheckBox("Bots rebuy and top up")
        self.bots_rebuy_check.setChecked(DEFAULT_SETTINGS.bots_rebuy)
        self.bots_rebuy_check.setToolTip(
            "A busted bot buys in again and a short one tops up: the table "
            "stays full. Off: busted bots leave the table."
        )
        self.auto_top_up_check = QCheckBox("Auto top-up")
        self.auto_top_up_check.setToolTip(
            "Before every hand, your stack goes back to the maximum buy-in, "
            "paid from the bankroll."
        )
        table_options = QWidget()
        options_layout = QHBoxLayout(table_options)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(14)
        options_layout.addWidget(self.straddle_check)
        options_layout.addWidget(self.bots_rebuy_check)
        options_layout.addWidget(self.auto_top_up_check)
        options_layout.addStretch()
        self.table_options = table_options

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
        form.addRow("Opponents", self.bot_picker.count_widget)
        form.addRow("Bots", self.bot_picker.style_widget)
        form.addRow("Game", self.betting_picker)
        form.addRow("Starting stack", self.stack_spin)
        form.addRow("Blinds", self.blinds_combo)
        form.addRow("Table", self.table_options)
        form.addRow("Action clock", self.clock_combo)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(680)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(28, 26, 28, 26)
        panel_layout.setSpacing(16)
        panel_layout.addLayout(form)
        panel_layout.addWidget(self.buy_in_info)
        panel_layout.addWidget(self.error_label)
        panel_layout.addWidget(self.play_button)
        panel_layout.addWidget(self.back_button)

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.addWidget(self.bankroll_bar, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(24)
        layout.addWidget(panel, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        self.setLayout(scrolling(layout))

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
            opponents=self.bot_picker.opponents(),
            starting_stack=self.stack_spin.value(),
            small_blind=small_blind,
            big_blind=big_blind,
            straddle=self.straddle_check.isChecked(),
            betting=self.betting_picker.rules(),
            bots_rebuy=self.bots_rebuy_check.isChecked(),
            auto_top_up=self.auto_top_up_check.isChecked(),
        )

    def _apply_buy_in_range(self, stack: int) -> None:
        buy_in = BuyInRange.for_big_blind(self._big_blind)
        self.stack_spin.setRange(buy_in.minimum, buy_in.maximum)
        self.stack_spin.setSingleStep(10 * self._big_blind)
        self.stack_spin.setValue(buy_in.clamp(stack))

    def _on_blinds_changed(self) -> None:
        """The buy-in keeps its size in big blinds at the new blinds."""
        _, big_blind = self.blinds_combo.currentData()
        big_blinds = self.stack_spin.value() / self._big_blind
        self._big_blind = big_blind
        self._apply_buy_in_range(round(big_blinds * big_blind))

    def _on_play_clicked(self) -> None:
        try:
            settings = self.current_settings()
        except ValueError as error:
            self.error_label.setText(str(error))
            return

        self.error_label.clear()
        self.start_requested.emit(settings)
