"""The bots of a tournament, managed in a window of their own (V3.1).

The tournament setup shows how many bots play and a summary of their
styles; this window lists every bot (name and play style) to add, rename,
restyle or remove them, or draws a whole field at random for a difficulty:
Easy (no Shark or Adaptive), Normal or Hard (mostly strong bots).
"""

import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QAbstractItemModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.application.setup import MAX_BOT_NAME_LENGTH, bot_names, check_bot_names
from backend.application.tournament import MAX_ENTRANTS
from backend.bots.factory import (
    BOT_TYPES,
    DIFFICULTY_LABELS,
    Difficulty,
    random_styles,
)
from frontend.components.bot_picker import bot_combo, help_button

MAX_BOTS = MAX_ENTRANTS - 1
NAME_COLUMN = 0
STYLE_COLUMN = 1
STYLE_ROLE = Qt.ItemDataRole.UserRole
WINDOW_SIZE = (640, 640)


@dataclass(frozen=True)
class FieldBot:
    """One bot of a tournament field."""

    name: str
    style: str


def random_field(
    count: int,
    difficulty: Difficulty,
    rng: random.Random,
    player_name: str,
    keep: Sequence[FieldBot] = (),
) -> list[FieldBot]:
    """``keep`` and enough bots drawn at random to make ``count`` bots."""
    missing = max(0, count - len(keep))
    taken = {player_name, *(bot.name for bot in keep)}
    names = bot_names(missing, taken)
    styles = random_styles(missing, difficulty, rng)

    return [*keep[:count], *map(FieldBot, names, styles)]


def describe_field(field: Sequence[FieldBot]) -> str:
    """'7 bots: TAG ×3 · Shark ×2 · Nit · LAG' (most common style first)."""
    counts = Counter(bot.style for bot in field)
    parts = [
        BOT_TYPES[style].label + (f" ×{count}" if count > 1 else "")
        for style, count in counts.most_common()
    ]
    noun = "bot" if len(field) == 1 else "bots"

    return f"{len(field)} {noun}: " + " · ".join(parts)


def difficulty_combo() -> QComboBox:
    combo = QComboBox()

    for difficulty, label in DIFFICULTY_LABELS.items():
        combo.addItem(label, difficulty)

    combo.setCurrentIndex(combo.findData(Difficulty.NORMAL))

    return combo


class StyleDelegate(QStyledItemDelegate):
    """Edits a bot's play style with a list of the styles."""

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget:
        return bot_combo(index.data(STYLE_ROLE), parent)

    def setEditorData(
        self, editor: QWidget, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        if isinstance(editor, QComboBox):
            editor.setCurrentIndex(editor.findData(index.data(STYLE_ROLE)))

    def setModelData(
        self,
        editor: QWidget,
        model: QAbstractItemModel,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentData(), STYLE_ROLE)
            model.setData(index, editor.currentText(), Qt.ItemDataRole.DisplayRole)


class BotManagerDialog(QDialog):
    """Every bot of the tournament: names and play styles."""

    def __init__(
        self,
        field: Sequence[FieldBot],
        player_name: str,
        difficulty: Difficulty = Difficulty.NORMAL,
        rng: random.Random | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settingsDialog")
        self.setWindowTitle("Tournament bots")
        self.resize(*WINDOW_SIZE)
        self.player_name = player_name
        self._rng = rng or random.Random()

        # A whole field at random.
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, MAX_BOTS)
        self.count_spin.setValue(len(field))
        self.count_spin.setSuffix(" bots")
        self.difficulty_combo = difficulty_combo()
        self.difficulty_combo.setCurrentIndex(
            self.difficulty_combo.findData(difficulty)
        )
        self.draw_button = QPushButton("Draw at random")
        self.draw_button.setObjectName("accent")
        self.draw_button.setToolTip("Replaces the list: names and styles at random.")
        self.draw_button.clicked.connect(self.draw)

        random_box = QGroupBox("Random field")
        random_layout = QHBoxLayout(random_box)
        random_layout.addWidget(self.count_spin)
        random_layout.addWidget(self.difficulty_combo, stretch=1)
        random_layout.addWidget(self.draw_button)

        # The list.
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Name", "Play style"])
        self.table.setItemDelegateForColumn(STYLE_COLUMN, StyleDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self._refresh_summary)

        # Editing the list.
        self.style_combo = bot_combo("tag")
        self.add_spin = QSpinBox()
        self.add_spin.setRange(1, MAX_BOTS)
        self.add_button = QPushButton("Add")
        self.add_button.setToolTip("Adds bots of this style at the end of the list.")
        self.add_button.clicked.connect(self.add_bots)
        self.restyle_button = QPushButton("Set style")
        self.restyle_button.setToolTip("Gives this style to the selected bots.")
        self.restyle_button.clicked.connect(self.restyle_selected)
        self.remove_button = QPushButton("Remove")
        self.remove_button.setObjectName("danger")
        self.remove_button.setToolTip("Removes the selected bots.")
        self.remove_button.clicked.connect(self.remove_selected)

        edit_row = QHBoxLayout()
        edit_row.addWidget(self.style_combo, stretch=1)
        edit_row.addWidget(self.add_spin)
        edit_row.addWidget(self.add_button)
        edit_row.addWidget(self.restyle_button)
        edit_row.addWidget(self.remove_button)
        edit_row.addWidget(help_button())

        hint = QLabel(
            "Double-click a name or a style to change it. Select several bots "
            "(Ctrl or Shift) to restyle or remove them together."
        )
        hint.setObjectName("hintText")
        hint.setWordWrap(True)
        self.summary_label = QLabel()
        self.summary_label.setObjectName("summaryText")
        self.summary_label.setWordWrap(True)
        self.error_label = QLabel()
        self.error_label.setObjectName("errorText")
        self.error_label.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(random_box)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(edit_row)
        layout.addWidget(hint)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.error_label)
        layout.addWidget(buttons)

        self.set_field(field)

    # --- The list -----------------------------------------------------------

    @property
    def difficulty(self) -> Difficulty:
        return Difficulty(self.difficulty_combo.currentData())

    def field(self) -> list[FieldBot]:
        """The bots as listed, names trimmed."""
        return [
            FieldBot(self._name_item(row).text().strip(), self._style(row))
            for row in range(self.table.rowCount())
        ]

    def set_field(self, field: Sequence[FieldBot]) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self._append(field)
        self.table.blockSignals(False)
        self._refresh_summary()

    def draw(self) -> None:
        """A new field of ``count`` bots at random, for the difficulty."""
        self.set_field(
            random_field(
                self.count_spin.value(), self.difficulty, self._rng, self.player_name
            )
        )

    def add_bots(self) -> None:
        room = MAX_BOTS - self.table.rowCount()
        count = min(self.add_spin.value(), room)

        if count <= 0:
            self.error_label.setText(f"A tournament has at most {MAX_BOTS} bots.")
            return

        taken = {self.player_name, *(bot.name for bot in self.field())}
        style = self.style_combo.currentData()
        self.table.blockSignals(True)
        self._append([FieldBot(name, style) for name in bot_names(count, taken)])
        self.table.blockSignals(False)
        self.table.scrollToBottom()
        self._refresh_summary()

    def restyle_selected(self) -> None:
        style = self.style_combo.currentData()
        self.table.blockSignals(True)

        for row in self._selected_rows():
            self._set_style(row, style)

        self.table.blockSignals(False)
        self._refresh_summary()

    def remove_selected(self) -> None:
        rows = self._selected_rows()

        if len(rows) >= self.table.rowCount():
            self.error_label.setText("A tournament needs at least one bot.")
            return

        self.table.blockSignals(True)

        for row in sorted(rows, reverse=True):
            self.table.removeRow(row)

        self.table.blockSignals(False)
        self._refresh_summary()

    def accept(self) -> None:
        field = self.field()

        try:
            check_bot_names(
                tuple(bot.name for bot in field), len(field), self.player_name
            )
        except ValueError as error:
            self.error_label.setText(str(error))
            return

        super().accept()

    # --- Helpers ------------------------------------------------------------

    def _append(self, bots: Sequence[FieldBot]) -> None:
        first = self.table.rowCount()
        self.table.setRowCount(first + len(bots))

        for row, bot in enumerate(bots, start=first):
            self.table.setItem(row, NAME_COLUMN, QTableWidgetItem(bot.name))
            self.table.setItem(row, STYLE_COLUMN, QTableWidgetItem())
            self._set_style(row, bot.style)

    def _set_style(self, row: int, style: str) -> None:
        item = self.table.item(row, STYLE_COLUMN)
        assert item is not None
        item.setData(STYLE_ROLE, style)
        item.setText(BOT_TYPES[style].label)
        item.setToolTip(BOT_TYPES[style].description)

    def _style(self, row: int) -> str:
        item = self.table.item(row, STYLE_COLUMN)
        assert item is not None

        return item.data(STYLE_ROLE)

    def _name_item(self, row: int) -> QTableWidgetItem:
        item = self.table.item(row, NAME_COLUMN)
        assert item is not None

        return item

    def _selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.table.selectedIndexes()})

    def _refresh_summary(self) -> None:
        field = self.field()
        self.summary_label.setText(describe_field(field))
        self.count_spin.setValue(max(1, len(field)))
        self.error_label.clear()

        too_long = [bot.name for bot in field if len(bot.name) > MAX_BOT_NAME_LENGTH]

        if too_long:
            self.error_label.setText(
                f"Names are at most {MAX_BOT_NAME_LENGTH} characters long."
            )
