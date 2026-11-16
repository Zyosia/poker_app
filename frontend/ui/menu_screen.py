"""Main menu and game configuration."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from backend.application.setup import BotLevel, GameSettings
from backend.poker_engine.constants import MAX_TABLE_SEATS

BLIND_LEVELS = ((5, 10), (10, 20), (25, 50), (50, 100))
BOT_LEVEL_LABELS = {
    BotLevel.NORMAL: "Normal — plays its hand strength",
    BotLevel.EASY: "Easy — plays randomly",
}
DEFAULT_SETTINGS = GameSettings()


class MenuScreen(QWidget):
    """Lets the user configure and start a game."""

    start_requested = Signal(GameSettings)
    quit_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        title = QLabel("♠ ♥  POKER  ♦ ♣")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("No Limit Texas Hold'em")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.name_edit = QLineEdit(DEFAULT_SETTINGS.player_name)
        self.name_edit.setMaxLength(12)

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

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #ff7b7b;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.play_button = QPushButton("Play")
        self.play_button.setObjectName("primary")
        self.play_button.setMinimumHeight(46)
        self.play_button.clicked.connect(self._on_play_clicked)
        self.quit_button = QPushButton("Quit")
        self.quit_button.clicked.connect(self.quit_requested)

        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(18)
        form.addRow("Your name", self.name_edit)
        form.addRow("Opponents", self.opponents_spin)
        form.addRow("Bot level", self.level_combo)
        form.addRow("Starting stack", self.stack_spin)
        form.addRow("Blinds", self.blinds_combo)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(460)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(28, 26, 28, 26)
        panel_layout.setSpacing(16)
        panel_layout.addLayout(form)
        panel_layout.addWidget(self.error_label)
        panel_layout.addWidget(self.play_button)
        panel_layout.addWidget(self.quit_button)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(24)
        layout.addWidget(panel, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

    def current_settings(self) -> GameSettings:
        """Return the settings currently entered in the form."""
        small_blind, big_blind = self.blinds_combo.currentData()

        return GameSettings(
            player_name=self.name_edit.text().strip(),
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
