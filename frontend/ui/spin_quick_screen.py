"""The first screen of a Spin & Go window: a buy-in starts a game at once (V3.2)."""

import random

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from backend.application.bankroll import DEFAULT_BALANCE, GameMode, bankroll_hint
from backend.application.setup import (
    DEFAULT_PLAYER_NAME,
    DEFAULT_QUICK_SPIN_DIFFICULTY,
    QUICK_SPIN_BUY_INS,
    QUICK_SPIN_CLOCK,
    SpinSettings,
    quick_spin_settings,
)
from backend.bots.factory import DIFFICULTY_LABELS, Difficulty
from frontend.components.bankroll_bar import BankrollBar
from frontend.formatting import format_chips

from .cash_setup_screen import scrolling
from .tournament_setup_screen import error_label

BUY_IN_COLUMNS = 6
DIFFICULTY_NAMES = {
    Difficulty.EASY: "Easy",
    Difficulty.NORMAL: "Normal",
    Difficulty.HARD: "Hard",
}
GAME_SUMMARY = (
    f"No Limit · no cap · levels by time · fair multipliers · "
    f"{QUICK_SPIN_CLOCK} action clock"
)


class SpinQuickScreen(QWidget):
    """A button per buy-in, the bots' difficulty, and the custom setup."""

    start_requested = Signal(SpinSettings)
    custom_requested = Signal()
    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rng = random.Random()
        """Draws the two bots (tests seed it)."""
        self.player_name = DEFAULT_PLAYER_NAME
        self._balance = DEFAULT_BALANCE
        self._hints = True

        self.bankroll_bar = BankrollBar()
        self.difficulty_group = QButtonGroup(self)
        self.difficulty_buttons: dict[Difficulty, QPushButton] = {}
        difficulty_row = QHBoxLayout()
        difficulty_row.setSpacing(6)

        for difficulty, name in DIFFICULTY_NAMES.items():
            button = QPushButton(name)
            button.setObjectName("toggle")
            button.setCheckable(True)
            button.setMinimumWidth(90)
            button.setToolTip(DIFFICULTY_LABELS[difficulty])
            self.difficulty_group.addButton(button)
            self.difficulty_buttons[difficulty] = button
            difficulty_row.addWidget(button)

        difficulty_row.addStretch()
        self.difficulty_buttons[DEFAULT_QUICK_SPIN_DIFFICULTY].setChecked(True)
        self.difficulty_label = QLabel()
        self.difficulty_label.setObjectName("hintText")
        self.difficulty_group.buttonToggled.connect(self._show_difficulty)
        self._show_difficulty()

        self.buy_in_buttons: dict[int, QPushButton] = {}
        grid = QGridLayout()
        grid.setSpacing(8)

        for index, buy_in in enumerate(QUICK_SPIN_BUY_INS):
            button = QPushButton(format_chips(buy_in))
            button.setObjectName("spinBuyIn")
            button.clicked.connect(lambda _=False, amount=buy_in: self.start(amount))
            self.buy_in_buttons[buy_in] = button
            grid.addWidget(button, *divmod(index, BUY_IN_COLUMNS))

        summary = QLabel(GAME_SUMMARY)
        summary.setObjectName("hintText")
        summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label = error_label()
        self.custom_button = QPushButton("Custom Spin && Go…")
        self.custom_button.setToolTip(
            "Choose the bots, the buy-in, the game, the multipliers and the clock."
        )
        self.custom_button.clicked.connect(self.custom_requested)
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.back_requested)

        self.setLayout(self._page(difficulty_row, grid, summary))
        self.refresh_buttons()

    def _page(
        self, difficulty_row: QHBoxLayout, grid: QGridLayout, summary: QLabel
    ) -> QVBoxLayout:
        title = QLabel("♥  SPIN & GO")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Pick a buy-in: the prize is drawn and the game starts")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        opponents = QLabel("OPPONENTS")
        opponents.setObjectName("sectionTitle")
        buy_ins = QLabel("BUY-IN")
        buy_ins.setObjectName("sectionTitle")

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(680)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(28, 24, 28, 24)
        panel_layout.setSpacing(12)
        panel_layout.addWidget(opponents)
        panel_layout.addLayout(difficulty_row)
        panel_layout.addWidget(self.difficulty_label)
        panel_layout.addSpacing(6)
        panel_layout.addWidget(buy_ins)
        panel_layout.addLayout(grid)
        panel_layout.addWidget(summary)
        panel_layout.addWidget(self.error_label)
        panel_layout.addSpacing(6)
        panel_layout.addWidget(self.custom_button)
        panel_layout.addWidget(self.back_button)

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.addWidget(self.bankroll_bar, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(18)
        layout.addWidget(panel, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

        return scrolling(layout)

    @property
    def difficulty(self) -> Difficulty:
        return next(
            difficulty
            for difficulty, button in self.difficulty_buttons.items()
            if button.isChecked()
        )

    def set_difficulty(self, difficulty: Difficulty) -> None:
        self.difficulty_buttons[difficulty].setChecked(True)

    def _show_difficulty(self) -> None:
        self.difficulty_label.setText(
            f"Two bots drawn at random: {DIFFICULTY_LABELS[self.difficulty]}."
        )

    def set_bankroll(self, balance: int, hints: bool) -> None:
        self._balance = balance
        self._hints = hints
        self.refresh_buttons()

    def set_player_name(self, name: str) -> None:
        self.player_name = name

    def refresh_buttons(self) -> None:
        """A buy-in the bankroll cannot pay is disabled; a large one warns."""
        for buy_in, button in self.buy_in_buttons.items():
            affordable = buy_in <= self._balance
            hint = bankroll_hint(GameMode.SPIN, buy_in, self._balance)
            button.setEnabled(affordable)

            if not affordable:
                tip = "Not enough money in your bankroll for this buy-in."
            elif self._hints and hint is not None:
                tip = hint
            else:
                tip = f"A Spin & Go for a {format_chips(buy_in)} buy-in."

            button.setToolTip(tip)

    def settings_for(self, buy_in: int) -> SpinSettings:
        """The game a buy-in button starts, with two bots drawn now."""
        return quick_spin_settings(buy_in, self.difficulty, self.player_name, self.rng)

    def start(self, buy_in: int) -> None:
        self.error_label.clear()
        self.start_requested.emit(self.settings_for(buy_in))
