"""Bot Arena setup: seats, play styles and simulation settings."""

import os

from PySide6.QtCore import QRegularExpression, Qt, Signal
from PySide6.QtGui import QRegularExpressionValidator
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

from backend.bots.factory import BOT_TYPES
from backend.poker_engine.constants import MAX_TABLE_SEATS
from backend.simulation.config import (
    MIN_TABLE_SEATS,
    SeatSpec,
    SimulationConfig,
    StackPolicy,
)

from .cash_setup_screen import BLIND_LEVELS

HAND_PRESETS = (1_000, 10_000, 100_000)
CUSTOM = "custom"

ARENA_PRESETS: dict[str, tuple[str, ...]] = {
    "TAG vs 3 Maniacs": ("tag", "maniac", "maniac", "maniac"),
    "Full styles table (6-max)": ("nit", "tag", "lag", "station", "maniac", "basic"),
    "Heads-up: TAG vs Calling Station": ("tag", "station"),
    "Tight vs loose (4-max)": ("nit", "tag", "lag", "maniac"),
}

POLICY_LABELS = {
    StackPolicy.RESET_EACH_HAND: "Reset each hand",
    StackPolicy.AUTO_REBUY: "Auto rebuy",
    StackPolicy.ELIMINATION: "Elimination",
}

DUPLICATE_TOOLTIP = (
    "Plays every deal once per seat rotation, so luck evens out between bots."
)
DUPLICATE_DISABLED_TOOLTIP = (
    "Duplicate mode needs the 'Reset each hand' policy: with rebuys or "
    "eliminations, stacks differ between rotations of a deal."
)


def default_worker_count() -> int:
    return max(1, (os.cpu_count() or 2) - 1)


class SeatRow(QWidget):
    """One seat: play style, optional name and a remove button."""

    remove_requested = Signal(object)

    def __init__(self, bot: str = "tag", parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.profile_combo = QComboBox()

        for bot_type in BOT_TYPES.values():
            self.profile_combo.addItem(bot_type.label, bot_type.key)
            self.profile_combo.setItemData(
                self.profile_combo.count() - 1,
                bot_type.description,
                Qt.ItemDataRole.ToolTipRole,
            )

        self.description_label = QLabel()
        self.description_label.setObjectName("modeDescription")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Name (optional)")
        self.name_edit.setMaxLength(16)
        self.name_edit.setFixedWidth(150)
        self.remove_button = QPushButton("✕")
        self.remove_button.setObjectName("small")
        self.remove_button.setToolTip("Remove this seat")
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))

        self.profile_combo.currentIndexChanged.connect(self._update_description)
        self.set_bot(bot)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.profile_combo)
        layout.addWidget(self.description_label, stretch=1)
        layout.addWidget(self.name_edit)
        layout.addWidget(self.remove_button)

    @property
    def bot(self) -> str:
        return self.profile_combo.currentData()

    def set_bot(self, bot: str) -> None:
        self.profile_combo.setCurrentIndex(self.profile_combo.findData(bot))
        self._update_description()

    def seat_spec(self) -> SeatSpec:
        return SeatSpec(bot=self.bot, name=self.name_edit.text().strip() or None)

    def _update_description(self) -> None:
        self.description_label.setText(BOT_TYPES[self.bot].description)


class ArenaSetupScreen(QWidget):
    """Configures a Bot Arena run, played fast or watched on the table."""

    run_requested = Signal(SimulationConfig)
    watch_requested = Signal(SimulationConfig)
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        title = QLabel("♦  BOT ARENA")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Compare play styles over thousands of hands")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Choose a preset table…", None)

        for name in ARENA_PRESETS:
            self.preset_combo.addItem(name, name)

        self.preset_combo.currentIndexChanged.connect(self._on_preset_chosen)

        self.seat_rows: list[SeatRow] = []
        self.seats_layout = QVBoxLayout()
        self.seats_layout.setSpacing(8)
        self.add_seat_button = QPushButton("+ Add seat")
        self.add_seat_button.setObjectName("small")
        self.add_seat_button.clicked.connect(lambda: self.add_seat("tag"))

        self._build_settings()

        self.error_label = QLabel()
        self.error_label.setObjectName("errorText")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)

        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.back_requested)
        self.watch_button = QPushButton("Watch")
        self.watch_button.setObjectName("accent")
        self.watch_button.setToolTip("Play the hands on the table, at your pace.")
        self.watch_button.clicked.connect(self._on_watch_clicked)
        self.run_button = QPushButton("Run fast")
        self.run_button.setObjectName("primary")
        self.run_button.setToolTip("Simulate in the background, then show the stats.")
        self.run_button.clicked.connect(self._on_run_clicked)

        self._build_layout(title, subtitle)
        self.set_seats(ARENA_PRESETS["TAG vs 3 Maniacs"])

    def _build_settings(self) -> None:
        self.hands_combo = QComboBox()

        for hands in HAND_PRESETS:
            self.hands_combo.addItem(f"{hands:,}".replace(",", " "), hands)

        self.hands_combo.addItem("Custom", CUSTOM)
        self.hands_combo.setCurrentIndex(1)
        self.hands_spin = QSpinBox()
        self.hands_spin.setRange(1, 10_000_000)
        self.hands_spin.setSingleStep(1000)
        self.hands_spin.setValue(5000)
        self.hands_combo.currentIndexChanged.connect(self._update_visibility)

        self.sessions_spin = QSpinBox()
        self.sessions_spin.setRange(1, 100_000)
        self.sessions_spin.setValue(100)

        self.blinds_combo = QComboBox()

        for small_blind, big_blind in BLIND_LEVELS:
            self.blinds_combo.addItem(
                f"{small_blind} / {big_blind}", (small_blind, big_blind)
            )

        self.stack_spin = QSpinBox()
        self.stack_spin.setRange(100, 1_000_000)
        self.stack_spin.setSingleStep(100)
        self.stack_spin.setValue(1000)

        self.policy_combo = QComboBox()

        for policy, label in POLICY_LABELS.items():
            self.policy_combo.addItem(label, policy)

        self.policy_combo.currentIndexChanged.connect(self._update_visibility)

        self.seed_edit = QLineEdit()
        self.seed_edit.setPlaceholderText("Random")
        self.seed_edit.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"\d{0,18}"))
        )

        self.duplicate_check = QCheckBox("Duplicate mode (variance reduction)")
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, max(1, os.cpu_count() or 1))
        self.workers_spin.setValue(default_worker_count())
        self.workers_spin.setToolTip("Processes used by the fast mode.")

        hands_row = QHBoxLayout()
        hands_row.addWidget(self.hands_combo)
        hands_row.addWidget(self.hands_spin)

        self.form = QFormLayout()
        self.form.setVerticalSpacing(10)
        self.form.setHorizontalSpacing(18)
        self.form.addRow("Hands", hands_row)
        self.form.addRow("Sessions", self.sessions_spin)
        self.form.addRow("Blinds", self.blinds_combo)
        self.form.addRow("Starting stack", self.stack_spin)
        self.form.addRow("Stack policy", self.policy_combo)
        self.form.addRow("Seed", self.seed_edit)
        self.form.addRow("Workers", self.workers_spin)
        self.form.addRow("", self.duplicate_check)

        self._update_visibility()

    def _build_layout(self, title: QLabel, subtitle: QLabel) -> None:
        seats_title = QLabel("SEATS")
        seats_title.setObjectName("sectionTitle")
        settings_title = QLabel("SETTINGS")
        settings_title.setObjectName("sectionTitle")

        seats_header = QHBoxLayout()
        seats_header.addWidget(seats_title)
        seats_header.addStretch()
        seats_header.addWidget(self.preset_combo)

        seats_panel = QFrame()
        seats_panel.setObjectName("panel")
        seats_layout = QVBoxLayout(seats_panel)
        seats_layout.setContentsMargins(20, 16, 20, 16)
        seats_layout.addLayout(seats_header)
        seats_layout.addLayout(self.seats_layout)
        seats_layout.addWidget(
            self.add_seat_button, alignment=Qt.AlignmentFlag.AlignLeft
        )
        seats_layout.addStretch()

        settings_panel = QFrame()
        settings_panel.setObjectName("panel")
        settings_panel.setFixedWidth(420)
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setContentsMargins(20, 16, 20, 16)
        settings_layout.addWidget(settings_title)
        settings_layout.addLayout(self.form)
        settings_layout.addStretch()

        panels = QHBoxLayout()
        panels.setSpacing(16)
        panels.addWidget(seats_panel, stretch=1)
        panels.addWidget(settings_panel)

        buttons = QHBoxLayout()
        buttons.addWidget(self.back_button)
        buttons.addStretch()
        buttons.addWidget(self.watch_button)
        buttons.addWidget(self.run_button)

        for button in (self.back_button, self.watch_button, self.run_button):
            button.setMinimumWidth(140)
            button.setMinimumHeight(44)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 20, 32, 24)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(10)
        layout.addLayout(panels, stretch=1)
        layout.addWidget(self.error_label)
        layout.addLayout(buttons)

    # --- Seats ---------------------------------------------------------------

    def add_seat(self, bot: str) -> SeatRow | None:
        if len(self.seat_rows) >= MAX_TABLE_SEATS:
            return None

        row = SeatRow(bot)
        row.remove_requested.connect(self.remove_seat)
        self.seat_rows.append(row)
        self.seats_layout.addWidget(row)
        self._update_seat_buttons()

        return row

    def remove_seat(self, row: SeatRow) -> None:
        if len(self.seat_rows) <= MIN_TABLE_SEATS or row not in self.seat_rows:
            return

        self.seat_rows.remove(row)
        self.seats_layout.removeWidget(row)
        row.deleteLater()
        self._update_seat_buttons()

    def set_seats(self, bots: tuple[str, ...]) -> None:
        """Replace every seat with the given bots."""
        for row in self.seat_rows:
            self.seats_layout.removeWidget(row)
            row.deleteLater()

        self.seat_rows = []

        for bot in bots:
            self.add_seat(bot)

    def _update_seat_buttons(self) -> None:
        self.add_seat_button.setEnabled(len(self.seat_rows) < MAX_TABLE_SEATS)

        for row in self.seat_rows:
            row.remove_button.setEnabled(len(self.seat_rows) > MIN_TABLE_SEATS)

    def _on_preset_chosen(self) -> None:
        name = self.preset_combo.currentData()

        if name is not None:
            self.set_seats(ARENA_PRESETS[name])

    # --- Settings ------------------------------------------------------------

    @property
    def stack_policy(self) -> StackPolicy:
        # Qt hands the enum back as a plain string.
        return StackPolicy(self.policy_combo.currentData())

    def _update_visibility(self) -> None:
        is_elimination = self.stack_policy == StackPolicy.ELIMINATION
        self.form.setRowVisible(0, not is_elimination)
        self.form.setRowVisible(1, is_elimination)
        self.hands_spin.setVisible(self.hands_combo.currentData() == CUSTOM)

        allows_duplicate = self.stack_policy == StackPolicy.RESET_EACH_HAND
        self.duplicate_check.setEnabled(allows_duplicate)
        self.duplicate_check.setToolTip(
            DUPLICATE_TOOLTIP if allows_duplicate else DUPLICATE_DISABLED_TOOLTIP
        )

        if not allows_duplicate:
            self.duplicate_check.setChecked(False)

    def hands(self) -> int:
        preset = self.hands_combo.currentData()

        return self.hands_spin.value() if preset == CUSTOM else preset

    def set_hands(self, hands: int) -> None:
        index = self.hands_combo.findData(hands)

        if index < 0:
            index = self.hands_combo.findData(CUSTOM)
            self.hands_spin.setValue(hands)

        self.hands_combo.setCurrentIndex(index)

    def current_config(self) -> SimulationConfig:
        """Build the configuration entered in the form; raises ValueError."""
        small_blind, big_blind = self.blinds_combo.currentData()
        seed_text = self.seed_edit.text().strip()

        return SimulationConfig(
            seats=tuple(row.seat_spec() for row in self.seat_rows),
            hands=self.hands(),
            sessions=self.sessions_spin.value(),
            small_blind=small_blind,
            big_blind=big_blind,
            starting_stack=self.stack_spin.value(),
            stack_policy=self.stack_policy,
            seed=int(seed_text) if seed_text else None,
            workers=self.workers_spin.value(),
            duplicate=self.duplicate_check.isChecked(),
        )

    def show_last_seed(self, seed: int) -> None:
        """Remind the seed of the last run when the seed was left random."""
        self.seed_edit.setPlaceholderText(f"Random (last run: {seed})")

    def _config_or_error(self) -> SimulationConfig | None:
        try:
            config = self.current_config()
        except ValueError as error:
            self.error_label.setText(str(error))
            return None

        self.error_label.clear()

        return config

    def _on_run_clicked(self) -> None:
        if (config := self._config_or_error()) is not None:
            self.run_requested.emit(config)

    def _on_watch_clicked(self) -> None:
        if (config := self._config_or_error()) is not None:
            self.watch_requested.emit(config)
