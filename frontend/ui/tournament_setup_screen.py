"""Setup of a Tournament and of a Spin & Go against bots."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from backend.application.action_clock import SPIN_CLOCK, tournament_clock
from backend.application.bankroll import DEFAULT_BALANCE, GameMode
from backend.application.payouts import (
    MULTIPLIER_TABLES,
    PAYOUT_PRESETS,
    PayoutStructure,
)
from backend.application.setup import (
    LEVELS_BY_HANDS,
    LEVELS_BY_TIME,
    SPIN_BUY_INS,
    TOURNAMENT_BUY_INS,
    SpinSettings,
    TournamentSettings,
)
from backend.application.structures import TOURNAMENT_STRUCTURES
from frontend.components.bankroll_bar import BankrollBar
from frontend.components.bot_picker import BotPicker, bot_combo
from frontend.components.buy_in_info import BuyInInfo
from frontend.components.clock_combo import ClockCombo
from frontend.formatting import format_chips

from .cash_setup_screen import player_name_label, scrolling

DEFAULT_TOURNAMENT = TournamentSettings()
DEFAULT_SPIN = SpinSettings()


def level_speed_combo() -> QComboBox:
    combo = QComboBox()
    combo.addItem("By hands", LEVELS_BY_HANDS)
    combo.addItem("By time (Pause freezes the clock)", LEVELS_BY_TIME)

    return combo


CUSTOM = "Custom"


class BuyInChoice(QWidget):
    """Buy-in presets, or any custom amount (0 for a freeroll)."""

    def __init__(self, presets: tuple[int, ...], default: int) -> None:
        super().__init__()
        self.combo = QComboBox()

        for amount in presets:
            self.combo.addItem(format_chips(amount), amount)

        self.combo.addItem(CUSTOM, None)
        self.spin = QSpinBox()
        self.spin.setRange(0, 1_000_000)
        self.spin.setSingleStep(100)
        self.spin.setGroupSeparatorShown(True)
        self.spin.setValue(default)
        self._sync_combo()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.combo, stretch=1)
        layout.addWidget(self.spin)

        self.combo.activated.connect(self._on_preset)
        self.spin.valueChanged.connect(self._sync_combo)

    def value(self) -> int:
        return self.spin.value()

    def _on_preset(self, index: int) -> None:
        amount = self.combo.itemData(index)

        if amount is not None:
            self.spin.setValue(amount)

    def _sync_combo(self) -> None:
        index = self.combo.findData(self.spin.value())
        self.combo.setCurrentIndex(index if index >= 0 else self.combo.count() - 1)


def setup_page(
    title_text: str,
    subtitle_text: str,
    form: QFormLayout,
    buttons: list[QWidget],
    bankroll_bar: BankrollBar,
) -> QVBoxLayout:
    """The common look of a setup screen: bankroll, title, panel, buttons."""
    title = QLabel(title_text)
    title.setObjectName("title")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    subtitle = QLabel(subtitle_text)
    subtitle.setObjectName("subtitle")
    subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

    panel = QFrame()
    panel.setObjectName("panel")
    panel.setFixedWidth(680)
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(28, 24, 28, 24)
    panel_layout.setSpacing(14)
    panel_layout.addLayout(form)

    for button in buttons:
        panel_layout.addWidget(button)

    layout = QVBoxLayout()
    layout.setSpacing(10)
    layout.addWidget(bankroll_bar, alignment=Qt.AlignmentFlag.AlignRight)
    layout.addStretch()
    layout.addWidget(title)
    layout.addWidget(subtitle)
    layout.addSpacing(18)
    layout.addWidget(panel, alignment=Qt.AlignmentFlag.AlignHCenter)
    layout.addStretch()

    return scrolling(layout)


def error_label() -> QLabel:
    label = QLabel()
    label.setObjectName("errorText")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)

    return label


class TournamentSetupScreen(QWidget):
    """You against 1 to 8 bots, with rising blinds."""

    start_requested = Signal(TournamentSettings)
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.bankroll_bar = BankrollBar()
        self.name_label = player_name_label(DEFAULT_TOURNAMENT.player_name)
        self.bot_picker = BotPicker(DEFAULT_TOURNAMENT.opponents)
        self.opponents_spin = self.bot_picker.opponents_spin
        self.same_style_check = self.bot_picker.same_style_check
        self.bot_combos = self.bot_picker.bot_combos

        self.stack_spin = QSpinBox()
        self.stack_spin.setRange(100, 100_000)
        self.stack_spin.setSingleStep(100)
        self.stack_spin.setValue(DEFAULT_TOURNAMENT.starting_stack)
        self.structure_combo = QComboBox()

        for structure in TOURNAMENT_STRUCTURES:
            self.structure_combo.addItem(
                f"{structure.name} — {structure.hands_per_level} hands or "
                f"{structure.minutes_per_level:g} min per level",
                structure.name,
            )

        self.speed_combo = level_speed_combo()
        self.buy_in_choice = BuyInChoice(TOURNAMENT_BUY_INS, DEFAULT_TOURNAMENT.buy_in)
        self.buy_in_spin = self.buy_in_choice.spin
        self.payout_combo = QComboBox()
        self.payout_combo.addItem("Default (by number of players)", None)

        for payout in PAYOUT_PRESETS:
            self.payout_combo.addItem(payout.name, payout)

        self.rebuys_check = QCheckBox("Rebuys during 3 levels, then an add-on")
        self.clock_combo = ClockCombo(tournament_clock(DEFAULT_TOURNAMENT.structure))
        self.structure_combo.setCurrentIndex(
            self.structure_combo.findData(DEFAULT_TOURNAMENT.structure)
        )
        self.structure_combo.currentIndexChanged.connect(
            lambda: self.clock_combo.follow_default(
                tournament_clock(self.structure_combo.currentData())
            )
        )

        self.buy_in_info = BuyInInfo(GameMode.TOURNAMENT)
        self._balance = DEFAULT_BALANCE
        self._hints = True
        self.error_label = error_label()
        self.start_button = QPushButton("Start the tournament")
        self.start_button.setObjectName("primary")
        self.start_button.setMinimumHeight(46)
        self.start_button.clicked.connect(self._on_start_clicked)
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.back_requested)

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(18)
        form.addRow("Your name", self.name_label)
        form.addRow("Opponents", self.bot_picker.count_widget)
        form.addRow("Bots", self.bot_picker.style_widget)
        form.addRow("Starting stack", self.stack_spin)
        form.addRow("Blind structure", self.structure_combo)
        form.addRow("Level speed", self.speed_combo)
        form.addRow("Buy-in", self.buy_in_choice)
        form.addRow("Payout", self.payout_combo)
        form.addRow("", self.rebuys_check)
        form.addRow("Action clock", self.clock_combo)

        self.setLayout(
            setup_page(
                "♣  TOURNAMENT",
                "Rising blinds until one player holds every chip",
                form,
                [
                    self.buy_in_info,
                    self.error_label,
                    self.start_button,
                    self.back_button,
                ],
                self.bankroll_bar,
            )
        )
        self.buy_in_spin.valueChanged.connect(self.refresh_cost)
        self.refresh_cost()

    def opponents(self) -> tuple[str, ...]:
        return self.bot_picker.opponents()

    def cost(self) -> int:
        return self.buy_in_spin.value()

    def set_bankroll(self, balance: int, hints: bool) -> None:
        self._balance = balance
        self._hints = hints
        self.refresh_cost()

    def set_player_name(self, name: str) -> None:
        self.name_label.setText(name)

    def refresh_cost(self) -> None:
        affordable = self.buy_in_info.refresh(self.cost(), self._balance, self._hints)
        self.start_button.setEnabled(affordable)

    def current_settings(self) -> TournamentSettings:
        payout: PayoutStructure | None = self.payout_combo.currentData()

        return TournamentSettings(
            player_name=self.name_label.text(),
            opponents=self.opponents(),
            starting_stack=self.stack_spin.value(),
            structure=self.structure_combo.currentData(),
            levels_by=self.speed_combo.currentData(),
            buy_in=self.buy_in_spin.value(),
            payout=payout,
            rebuys=self.rebuys_check.isChecked(),
        )

    def _on_start_clicked(self) -> None:
        try:
            settings = self.current_settings()
        except ValueError as error:
            self.error_label.setText(str(error))
            return

        self.error_label.clear()
        self.start_requested.emit(settings)


class SpinSetupScreen(QWidget):
    """You against two bots, hyper-turbo, for a random prize."""

    start_requested = Signal(SpinSettings)
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.bankroll_bar = BankrollBar()
        self.name_label = player_name_label(DEFAULT_SPIN.player_name)
        self.bot_combos = [bot_combo(bot) for bot in DEFAULT_SPIN.opponents]
        bots = QHBoxLayout()

        for combo in self.bot_combos:
            bots.addWidget(combo)

        self.buy_in_choice = BuyInChoice(SPIN_BUY_INS, DEFAULT_SPIN.buy_in)
        self.buy_in_spin = self.buy_in_choice.spin
        self.speed_combo = level_speed_combo()
        self.multipliers_combo = QComboBox()

        for table in MULTIPLIER_TABLES:
            self.multipliers_combo.addItem(table.name, table)

        self.clock_combo = ClockCombo(SPIN_CLOCK)

        self.buy_in_info = BuyInInfo(GameMode.SPIN)
        self._balance = DEFAULT_BALANCE
        self._hints = True
        self.error_label = error_label()
        self.start_button = QPushButton("Spin!")
        self.start_button.setObjectName("primary")
        self.start_button.setMinimumHeight(46)
        self.start_button.clicked.connect(self._on_start_clicked)
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.back_requested)

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(18)
        form.addRow("Your name", self.name_label)
        form.addRow("Opponents", bots)
        form.addRow("Buy-in", self.buy_in_choice)
        form.addRow("Level speed", self.speed_combo)
        form.addRow("Multipliers", self.multipliers_combo)
        form.addRow("Action clock", self.clock_combo)

        self.setLayout(
            setup_page(
                "♥  SPIN & GO",
                "Three players, hyper-turbo, a prize drawn before the first hand",
                form,
                [
                    self.buy_in_info,
                    self.error_label,
                    self.start_button,
                    self.back_button,
                ],
                self.bankroll_bar,
            )
        )
        self.buy_in_spin.valueChanged.connect(self.refresh_cost)
        self.refresh_cost()

    def cost(self) -> int:
        return self.buy_in_spin.value()

    def set_bankroll(self, balance: int, hints: bool) -> None:
        self._balance = balance
        self._hints = hints
        self.refresh_cost()

    def set_player_name(self, name: str) -> None:
        self.name_label.setText(name)

    def refresh_cost(self) -> None:
        affordable = self.buy_in_info.refresh(self.cost(), self._balance, self._hints)
        self.start_button.setEnabled(affordable)

    def current_settings(self) -> SpinSettings:
        first, second = (combo.currentData() for combo in self.bot_combos)

        return SpinSettings(
            player_name=self.name_label.text(),
            opponents=(first, second),
            buy_in=self.buy_in_spin.value(),
            levels_by=self.speed_combo.currentData(),
            multipliers=self.multipliers_combo.currentData(),
        )

    def _on_start_clicked(self) -> None:
        try:
            settings = self.current_settings()
        except ValueError as error:
            self.error_label.setText(str(error))
            return

        self.error_label.clear()
        self.start_requested.emit(settings)
