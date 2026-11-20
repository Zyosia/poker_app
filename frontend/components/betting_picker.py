"""The choice of the game: No Limit, Pot Limit or Fixed Limit, and its cap."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSpinBox, QWidget

from backend.application.game_modes import BETTING_LABELS
from backend.poker_engine.constants import (
    FIXED_LIMIT_BET_CAP,
    MIN_BET_CAP,
    NO_LIMIT,
    BettingRules,
    BettingStructure,
)

MAX_BET_CAP = 9
NO_CAP = MIN_BET_CAP - 1
"""The value of the cap box shown as "No cap" (or the usual Fixed Limit cap)."""

STRUCTURE_TIPS = {
    BettingStructure.NO_LIMIT: "Bet or raise any amount, up to your whole stack.",
    BettingStructure.POT_LIMIT: (
        "Bet or raise up to the size of the pot, your call included."
    ),
    BettingStructure.FIXED_LIMIT: (
        "Every bet and raise is one big blind before the turn, two big "
        f"blinds on the turn and the river; {FIXED_LIMIT_BET_CAP} bets per round."
    ),
}


class BettingPicker(QWidget):
    """A structure box and a cap box: the most bets and raises per round."""

    changed = Signal()

    def __init__(
        self, rules: BettingRules = NO_LIMIT, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.structure_combo = QComboBox()

        for structure, label in BETTING_LABELS.items():
            self.structure_combo.addItem(label, structure)
            self.structure_combo.setItemData(
                self.structure_combo.count() - 1,
                STRUCTURE_TIPS[structure],
                Qt.ItemDataRole.ToolTipRole,
            )

        self.cap_spin = QSpinBox()
        self.cap_spin.setRange(NO_CAP, MAX_BET_CAP)
        self.cap_spin.setSuffix(" bets")
        self.cap_spin.setToolTip(
            "The most bets and raises in one betting round (the big blind is "
            "the first pre-flop). Once reached, players can only call or fold."
        )
        cap_label = QLabel("Cap")
        cap_label.setObjectName("hintText")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.structure_combo, stretch=1)
        layout.addWidget(cap_label)
        layout.addWidget(self.cap_spin)

        self.set_rules(rules)
        self.structure_combo.currentIndexChanged.connect(self._on_structure_changed)
        self.cap_spin.valueChanged.connect(self.changed)

    def rules(self) -> BettingRules:
        cap = self.cap_spin.value()

        return BettingRules(
            self.structure_combo.currentData(), None if cap == NO_CAP else cap
        )

    def set_rules(self, rules: BettingRules) -> None:
        self.structure_combo.blockSignals(True)
        self.structure_combo.setCurrentIndex(
            self.structure_combo.findData(rules.structure)
        )
        self.structure_combo.blockSignals(False)
        self._show_no_cap_text()
        self.cap_spin.setValue(NO_CAP if rules.cap is None else rules.cap)
        self.structure_combo.setToolTip(STRUCTURE_TIPS[rules.structure])

    def _on_structure_changed(self) -> None:
        structure = self.structure_combo.currentData()
        self.structure_combo.setToolTip(STRUCTURE_TIPS[structure])
        self._show_no_cap_text()
        self.changed.emit()

    def _show_no_cap_text(self) -> None:
        fixed = self.structure_combo.currentData() == BettingStructure.FIXED_LIMIT
        self.cap_spin.setSpecialValueText(
            f"Usual ({FIXED_LIMIT_BET_CAP})" if fixed else "No cap"
        )
