"""The opponents of a game: how many bots, and the play style of each."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QWidget,
)

from backend.bots.factory import BOT_TYPES
from backend.poker_engine.constants import MAX_TABLE_SEATS
from frontend.ui.guide_window import open_guide

MAX_OPPONENTS = MAX_TABLE_SEATS - 1
COMBO_COLUMNS = 4
SAME_FOR_ALL = "Same style for every bot"
HELP_TOOLTIP = "What do the play styles mean? Opens the guide."


def help_button(bot: str | None = None) -> QPushButton:
    """A "?" button opening the bot styles of the guide (at ``bot``)."""
    button = QPushButton("?")
    button.setObjectName("help")
    button.setToolTip(HELP_TOOLTIP)
    button.clicked.connect(lambda: open_guide("bots", bot))

    return button


def bot_combo(bot: str, parent: QWidget | None = None) -> QComboBox:
    """A choice of play style, with its description as tooltip."""
    combo = QComboBox(parent)

    for bot_type in BOT_TYPES.values():
        combo.addItem(bot_type.label, bot_type.key)
        combo.setItemData(
            combo.count() - 1, bot_type.description, Qt.ItemDataRole.ToolTipRole
        )

    combo.setCurrentIndex(combo.findData(bot))

    return combo


class BotPicker:
    """1 bot (heads-up) to 8 (a full-ring table), one style each or the same.

    Two widgets, for two rows of a setup form: ``count_widget`` sets the
    number of bots (and whether they all play the same style),
    ``style_widget`` holds the style choices.
    """

    def __init__(self, defaults: tuple[str, ...]) -> None:
        self.opponents_spin = QSpinBox()
        self.opponents_spin.setRange(1, MAX_OPPONENTS)
        self.opponents_spin.setValue(len(defaults))
        self.opponents_spin.setToolTip(
            f"1 for heads-up, 5 for a 6-max table, {MAX_OPPONENTS} for full ring."
        )

        self.same_style_check = QCheckBox(SAME_FOR_ALL)
        self.help_button = help_button()
        self.bot_combos = [
            bot_combo(defaults[index % len(defaults)]) for index in range(MAX_OPPONENTS)
        ]

        self.count_widget = QWidget()
        count_layout = QHBoxLayout(self.count_widget)
        count_layout.setContentsMargins(0, 0, 0, 0)
        count_layout.setSpacing(14)
        count_layout.addWidget(self.opponents_spin, stretch=1)
        count_layout.addWidget(self.same_style_check)
        count_layout.addWidget(self.help_button)

        self.style_widget = QWidget()
        grid = QGridLayout(self.style_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        for index, combo in enumerate(self.bot_combos):
            grid.addWidget(combo, index // COMBO_COLUMNS, index % COMBO_COLUMNS)

        self.opponents_spin.valueChanged.connect(self._update)
        self.same_style_check.toggled.connect(self._update)
        self._update()

    def opponents(self) -> tuple[str, ...]:
        """The style key of every bot, in seat order."""
        count = self.opponents_spin.value()

        if self.same_style_check.isChecked():
            return (self.bot_combos[0].currentData(),) * count

        return tuple(combo.currentData() for combo in self.bot_combos[:count])

    def _update(self) -> None:
        shown = 1 if self.same_style_check.isChecked() else self.opponents_spin.value()

        for index, combo in enumerate(self.bot_combos):
            combo.setVisible(index < shown)
