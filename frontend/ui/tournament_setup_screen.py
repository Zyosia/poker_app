"""Setup of a Tournament and of a Spin & Go against bots."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from backend.application.payouts import (
    MULTIPLIER_TABLES,
    PAYOUT_PRESETS,
    PayoutStructure,
)
from backend.application.setup import (
    LEVELS_BY_HANDS,
    LEVELS_BY_TIME,
    SpinSettings,
    TournamentSettings,
)
from backend.application.structures import TOURNAMENT_STRUCTURES
from backend.bots.factory import BOT_TYPES
from backend.poker_engine.constants import MAX_TABLE_SEATS

DEFAULT_TOURNAMENT = TournamentSettings()
DEFAULT_SPIN = SpinSettings()
SAME_FOR_ALL = "Same style for every bot"


def bot_combo(bot: str) -> QComboBox:
    """A choice of play style, with its description as tooltip."""
    combo = QComboBox()

    for bot_type in BOT_TYPES.values():
        combo.addItem(bot_type.label, bot_type.key)
        combo.setItemData(
            combo.count() - 1, bot_type.description, Qt.ItemDataRole.ToolTipRole
        )

    combo.setCurrentIndex(combo.findData(bot))

    return combo


def level_speed_combo() -> QComboBox:
    combo = QComboBox()
    combo.addItem("By hands", LEVELS_BY_HANDS)
    combo.addItem("By time (Pause freezes the clock)", LEVELS_BY_TIME)

    return combo


def setup_page(
    title_text: str, subtitle_text: str, form: QFormLayout, buttons: list[QWidget]
) -> QVBoxLayout:
    """The common look of a setup screen: title, panel, buttons."""
    title = QLabel(title_text)
    title.setObjectName("title")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    subtitle = QLabel(subtitle_text)
    subtitle.setObjectName("subtitle")
    subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

    panel = QFrame()
    panel.setObjectName("panel")
    panel.setFixedWidth(560)
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(28, 24, 28, 24)
    panel_layout.setSpacing(14)
    panel_layout.addLayout(form)

    for button in buttons:
        panel_layout.addWidget(button)

    layout = QVBoxLayout()
    layout.setSpacing(10)
    layout.addStretch()
    layout.addWidget(title)
    layout.addWidget(subtitle)
    layout.addSpacing(18)
    layout.addWidget(panel, alignment=Qt.AlignmentFlag.AlignHCenter)
    layout.addStretch()

    return layout


def error_label() -> QLabel:
    label = QLabel()
    label.setObjectName("errorText")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)

    return label


class TournamentSetupScreen(QWidget):
    """You against 1 to 5 bots, with rising blinds."""

    start_requested = Signal(TournamentSettings)
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.name_edit = QLineEdit(DEFAULT_TOURNAMENT.player_name)
        self.name_edit.setMaxLength(12)
        self.opponents_spin = QSpinBox()
        self.opponents_spin.setRange(1, MAX_TABLE_SEATS - 1)
        self.opponents_spin.setValue(len(DEFAULT_TOURNAMENT.opponents))
        self.opponents_spin.valueChanged.connect(self._update_bots)

        self.same_style_check = QCheckBox(SAME_FOR_ALL)
        self.same_style_check.toggled.connect(self._update_bots)
        self.bot_combos = [
            bot_combo(DEFAULT_TOURNAMENT.opponents[index % 5])
            for index in range(MAX_TABLE_SEATS - 1)
        ]
        bots = QHBoxLayout()
        bots.setSpacing(6)

        for combo in self.bot_combos:
            bots.addWidget(combo)

        self.bots_row = QWidget()
        self.bots_row.setLayout(bots)
        bots.setContentsMargins(0, 0, 0, 0)

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
        self.buy_in_spin = QSpinBox()
        self.buy_in_spin.setRange(0, 1_000_000)
        self.buy_in_spin.setSingleStep(10)
        self.buy_in_spin.setValue(DEFAULT_TOURNAMENT.buy_in)
        self.payout_combo = QComboBox()
        self.payout_combo.addItem("Default (by number of players)", None)

        for payout in PAYOUT_PRESETS:
            self.payout_combo.addItem(payout.name, payout)

        self.rebuys_check = QCheckBox("Rebuys during 3 levels, then an add-on")

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
        form.addRow("Your name", self.name_edit)
        form.addRow("Opponents", self.opponents_spin)
        form.addRow("", self.same_style_check)
        form.addRow("Bots", self.bots_row)
        form.addRow("Starting stack", self.stack_spin)
        form.addRow("Blind structure", self.structure_combo)
        form.addRow("Level speed", self.speed_combo)
        form.addRow("Buy-in", self.buy_in_spin)
        form.addRow("Payout", self.payout_combo)
        form.addRow("", self.rebuys_check)

        self.setLayout(
            setup_page(
                "♣  TOURNAMENT",
                "Rising blinds until one player holds every chip",
                form,
                [self.error_label, self.start_button, self.back_button],
            )
        )
        self._update_bots()

    def _update_bots(self) -> None:
        count = 1 if self.same_style_check.isChecked() else self.opponents_spin.value()

        for index, combo in enumerate(self.bot_combos):
            combo.setVisible(index < count)

    def opponents(self) -> tuple[str, ...]:
        count = self.opponents_spin.value()

        if self.same_style_check.isChecked():
            return (self.bot_combos[0].currentData(),) * count

        return tuple(combo.currentData() for combo in self.bot_combos[:count])

    def current_settings(self) -> TournamentSettings:
        payout: PayoutStructure | None = self.payout_combo.currentData()

        return TournamentSettings(
            player_name=self.name_edit.text().strip(),
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

        self.name_edit = QLineEdit(DEFAULT_SPIN.player_name)
        self.name_edit.setMaxLength(12)
        self.bot_combos = [bot_combo(bot) for bot in DEFAULT_SPIN.opponents]
        bots = QHBoxLayout()

        for combo in self.bot_combos:
            bots.addWidget(combo)

        self.buy_in_spin = QSpinBox()
        self.buy_in_spin.setRange(1, 100_000)
        self.buy_in_spin.setValue(DEFAULT_SPIN.buy_in)
        self.speed_combo = level_speed_combo()
        self.multipliers_combo = QComboBox()

        for table in MULTIPLIER_TABLES:
            self.multipliers_combo.addItem(table.name, table)

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
        form.addRow("Your name", self.name_edit)
        form.addRow("Opponents", bots)
        form.addRow("Buy-in", self.buy_in_spin)
        form.addRow("Level speed", self.speed_combo)
        form.addRow("Multipliers", self.multipliers_combo)

        self.setLayout(
            setup_page(
                "♥  SPIN & GO",
                "Three players, hyper-turbo, a prize drawn before the first hand",
                form,
                [self.error_label, self.start_button, self.back_button],
            )
        )

    def current_settings(self) -> SpinSettings:
        first, second = (combo.currentData() for combo in self.bot_combos)

        return SpinSettings(
            player_name=self.name_edit.text().strip(),
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
