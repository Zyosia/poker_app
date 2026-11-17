"""Buttons and bet sizing controls of the human player."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.constants import ActionType
from frontend.formatting import big_blinds_to_chips, format_amount

BIG_BLIND_DECIMALS = 1
BUTTON_MIN_WIDTH = 120
"""Narrow enough for the hand history to fit beside a table window."""


class ActionPanel(QWidget):
    """Lets the user pick one of the legal actions.

    Only actions the engine reported as legal are enabled. Amounts are
    always chips internally; with a big blind set (``set_big_blind``) they
    are shown, and typed, in big blinds. The slider always moves in chips.
    """

    action_chosen = Signal(Action)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._legal: dict[ActionType, LegalAction] = {}
        self._pot = 0
        self._current_bet = 0
        self._player_bet = 0
        self._amount = 0
        """The "raise to" amount, in chips."""
        self._big_blind: int | None = None

        self.fold_button = QPushButton("Fold")
        self.fold_button.setObjectName("danger")
        self.call_button = QPushButton("Check")
        self.call_button.setObjectName("primary")
        self.raise_button = QPushButton("Bet")
        self.raise_button.setObjectName("accent")

        for button in (self.fold_button, self.call_button, self.raise_button):
            button.setMinimumHeight(48)
            button.setMinimumWidth(BUTTON_MIN_WIDTH)

        self.amount_slider = QSlider(Qt.Orientation.Horizontal)
        self.amount_spin = QDoubleSpinBox()
        """The amount in the display unit: chips, or big blinds."""
        self.amount_spin.setMinimumWidth(110)
        self.amount_spin.setGroupSeparatorShown(True)
        self.amount_spin.setDecimals(0)

        self.preset_buttons: dict[str, QPushButton] = {}
        presets_layout = QHBoxLayout()
        presets_layout.setSpacing(6)

        for label in ("Min", "1/2 Pot", "Pot", "Max"):
            button = QPushButton(label)
            button.setObjectName("small")
            button.clicked.connect(lambda _, name=label: self._apply_preset(name))
            self.preset_buttons[label] = button
            presets_layout.addWidget(button)

        sizing_layout = QHBoxLayout()
        sizing_layout.addWidget(self.amount_slider, stretch=1)
        sizing_layout.addWidget(self.amount_spin)

        raise_layout = QVBoxLayout()
        raise_layout.setSpacing(6)
        raise_layout.addLayout(presets_layout)
        raise_layout.addLayout(sizing_layout)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.fold_button)
        layout.addWidget(self.call_button)
        layout.addWidget(self.raise_button)
        layout.addLayout(raise_layout, stretch=1)

        self.fold_button.clicked.connect(lambda: self._emit(ActionType.FOLD))
        self.call_button.clicked.connect(self._on_call_clicked)
        self.raise_button.clicked.connect(self._on_raise_clicked)
        self.amount_slider.valueChanged.connect(self._set_amount)
        self.amount_spin.valueChanged.connect(self._on_spin_changed)

        self.set_legal_actions((), pot=0, current_bet=0, player_bet=0)

    @property
    def amount(self) -> int:
        """The "raise to" amount the raise button would send, in chips."""
        return self._amount

    @property
    def big_blind(self) -> int | None:
        return self._big_blind

    def set_big_blind(self, big_blind: int | None) -> None:
        """Show amounts in big blinds of ``big_blind``, or in chips (None)."""
        self._big_blind = big_blind
        self._configure_spin()
        self._update_labels()

    def set_legal_actions(
        self,
        legal_actions: tuple[LegalAction, ...],
        pot: int,
        current_bet: int,
        player_bet: int,
    ) -> None:
        """Enable exactly the given legal actions. An empty tuple disables all."""
        self._legal = {action.type: action for action in legal_actions}
        self._pot = pot
        self._current_bet = current_bet
        self._player_bet = player_bet

        self.fold_button.setEnabled(ActionType.FOLD in self._legal)
        self.call_button.setEnabled(
            ActionType.CHECK in self._legal or ActionType.CALL in self._legal
        )

        raise_action = self._legal.get(ActionType.RAISE)
        can_size = raise_action is not None

        for widget in (
            self.amount_slider,
            self.amount_spin,
            *self.preset_buttons.values(),
        ):
            widget.setEnabled(can_size)

        if raise_action is not None:
            minimum, maximum = self._raise_range(raise_action)
            self._amount = minimum
            self.amount_slider.blockSignals(True)
            self.amount_slider.setRange(minimum, maximum)
            self.amount_slider.setSingleStep(max(1, minimum - current_bet))
            self.amount_slider.setValue(minimum)
            self.amount_slider.blockSignals(False)

        self.raise_button.setEnabled(can_size or ActionType.ALL_IN in self._legal)
        self._configure_spin()
        self._update_labels()

    # --- Amounts --------------------------------------------------------------

    @staticmethod
    def _raise_range(raise_action: LegalAction) -> tuple[int, int]:
        assert raise_action.min_amount is not None
        assert raise_action.max_amount is not None

        return raise_action.min_amount, raise_action.max_amount

    def _to_display(self, chips: int) -> float:
        return chips if self._big_blind is None else chips / self._big_blind

    def _configure_spin(self) -> None:
        """Set the spin box's unit, range and value from the chip amount."""
        spin = self.amount_spin
        spin.blockSignals(True)
        in_big_blinds = self._big_blind is not None
        spin.setDecimals(BIG_BLIND_DECIMALS if in_big_blinds else 0)
        spin.setSuffix(" BB" if in_big_blinds else "")
        raise_action = self._legal.get(ActionType.RAISE)

        if raise_action is not None:
            minimum, maximum = self._raise_range(raise_action)
            step = self._to_display(max(1, minimum - self._current_bet))
            spin.setRange(self._to_display(minimum), self._to_display(maximum))
            spin.setSingleStep(max(step, 10**-BIG_BLIND_DECIMALS))
            spin.setValue(self._to_display(self._amount))

        spin.blockSignals(False)

    def _on_spin_changed(self, value: float) -> None:
        raise_action = self._legal.get(ActionType.RAISE)

        if raise_action is None:
            return

        minimum, maximum = self._raise_range(raise_action)

        if self._big_blind is None:
            chips = max(minimum, min(maximum, round(value)))
        else:
            chips = big_blinds_to_chips(value, self._big_blind, minimum, maximum)

            # The display is rounded to 0.1 BB: its ends mean the exact limits.
            if value >= self.amount_spin.maximum():
                chips = maximum
            elif value <= self.amount_spin.minimum():
                chips = minimum

        self._set_amount(chips, update_spin=False)

    def _set_amount(self, chips: int, update_spin: bool = True) -> None:
        """Make ``chips`` the raise amount and show it on every control."""
        self._amount = chips
        self.amount_slider.blockSignals(True)
        self.amount_slider.setValue(chips)
        self.amount_slider.blockSignals(False)

        if update_spin:
            self.amount_spin.blockSignals(True)
            self.amount_spin.setValue(self._to_display(chips))
            self.amount_spin.blockSignals(False)

        self._update_raise_label()

    def _apply_preset(self, name: str) -> None:
        raise_action = self._legal.get(ActionType.RAISE)

        if raise_action is None:
            return

        minimum, maximum = self._raise_range(raise_action)

        # Pot-sized raise: call first, then raise by the size of the pot.
        pot_after_call = self._pot + self._current_bet - self._player_bet
        targets = {
            "Min": minimum,
            "1/2 Pot": self._current_bet + pot_after_call // 2,
            "Pot": self._current_bet + pot_after_call,
            "Max": maximum,
        }

        self._set_amount(max(minimum, min(maximum, targets[name])))

    # --- Labels ---------------------------------------------------------------

    def _format(self, chips: int) -> str:
        return format_amount(chips, self._big_blind)

    def _update_labels(self) -> None:
        call_action = self._legal.get(ActionType.CALL)
        self.call_button.setText(
            f"Call {self._format(call_action.amount or 0)}"
            if call_action is not None
            else "Check"
        )
        self._update_raise_label()

    def _update_raise_label(self) -> None:
        raise_action = self._legal.get(ActionType.RAISE)
        all_in_action = self._legal.get(ActionType.ALL_IN)

        if raise_action is None:
            amount = all_in_action.amount if all_in_action is not None else None
            self.raise_button.setText(
                f"All-in {self._format(amount)}" if amount else "Bet"
            )
            return

        text = self._format(self._amount)

        if self._amount == raise_action.max_amount:
            self.raise_button.setText(f"All-in {text}")
        elif self._current_bet == 0:
            self.raise_button.setText(f"Bet {text}")
        else:
            self.raise_button.setText(f"Raise to {text}")

    # --- Actions ----------------------------------------------------------------

    def _on_call_clicked(self) -> None:
        if ActionType.CALL in self._legal:
            self._emit(ActionType.CALL)
        else:
            self._emit(ActionType.CHECK)

    def _on_raise_clicked(self) -> None:
        if ActionType.RAISE in self._legal:
            self._emit(ActionType.RAISE, amount=self._amount)
        else:
            self._emit(ActionType.ALL_IN)

    def _emit(self, action_type: ActionType, amount: int | None = None) -> None:
        self.action_chosen.emit(Action(type=action_type, amount=amount))
