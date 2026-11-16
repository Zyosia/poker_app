"""Buttons and bet sizing controls of the human player."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.constants import ActionType


class ActionPanel(QWidget):
    """Lets the user pick one of the legal actions.

    Only actions the engine reported as legal are enabled.
    """

    action_chosen = Signal(Action)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._legal: dict[ActionType, LegalAction] = {}
        self._pot = 0
        self._current_bet = 0
        self._player_bet = 0

        self.fold_button = QPushButton("Fold")
        self.fold_button.setObjectName("danger")
        self.call_button = QPushButton("Check")
        self.call_button.setObjectName("primary")
        self.raise_button = QPushButton("Bet")
        self.raise_button.setObjectName("accent")

        for button in (self.fold_button, self.call_button, self.raise_button):
            button.setMinimumHeight(48)
            button.setMinimumWidth(150)

        self.amount_slider = QSlider(Qt.Orientation.Horizontal)
        self.amount_spin = QSpinBox()
        self.amount_spin.setMinimumWidth(110)
        self.amount_spin.setGroupSeparatorShown(True)

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
        self.amount_slider.valueChanged.connect(self.amount_spin.setValue)
        self.amount_spin.valueChanged.connect(self._on_amount_changed)

        self.set_legal_actions((), pot=0, current_bet=0, player_bet=0)

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

        call_action = self._legal.get(ActionType.CALL)
        can_check = ActionType.CHECK in self._legal
        self.call_button.setEnabled(can_check or call_action is not None)
        self.call_button.setText(
            f"Call {call_action.amount}" if call_action is not None else "Check"
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
            assert raise_action.min_amount is not None
            assert raise_action.max_amount is not None

            for widget in (self.amount_slider, self.amount_spin):
                widget.blockSignals(True)
                widget.setRange(raise_action.min_amount, raise_action.max_amount)
                widget.setSingleStep(max(1, raise_action.min_amount - current_bet))
                widget.setValue(raise_action.min_amount)
                widget.blockSignals(False)

        self.raise_button.setEnabled(can_size or ActionType.ALL_IN in self._legal)
        self._update_raise_label()

    def _update_raise_label(self) -> None:
        raise_action = self._legal.get(ActionType.RAISE)
        all_in_action = self._legal.get(ActionType.ALL_IN)

        if raise_action is None:
            amount = all_in_action.amount if all_in_action is not None else None
            self.raise_button.setText(f"All-in {amount}" if amount else "Bet")
            return

        amount = self.amount_spin.value()

        if amount == raise_action.max_amount:
            self.raise_button.setText(f"All-in {amount}")
        elif self._current_bet == 0:
            self.raise_button.setText(f"Bet {amount}")
        else:
            self.raise_button.setText(f"Raise to {amount}")

    def _on_amount_changed(self, amount: int) -> None:
        self.amount_slider.blockSignals(True)
        self.amount_slider.setValue(amount)
        self.amount_slider.blockSignals(False)
        self._update_raise_label()

    def _apply_preset(self, name: str) -> None:
        raise_action = self._legal.get(ActionType.RAISE)

        if raise_action is None:
            return

        assert raise_action.min_amount is not None
        assert raise_action.max_amount is not None

        # Pot-sized raise: call first, then raise by the size of the pot.
        pot_after_call = self._pot + self._current_bet - self._player_bet
        targets = {
            "Min": raise_action.min_amount,
            "1/2 Pot": self._current_bet + pot_after_call // 2,
            "Pot": self._current_bet + pot_after_call,
            "Max": raise_action.max_amount,
        }

        # The spin box clamps the value to the legal range.
        self.amount_spin.setValue(targets[name])

    def _on_call_clicked(self) -> None:
        if ActionType.CALL in self._legal:
            self._emit(ActionType.CALL)
        else:
            self._emit(ActionType.CHECK)

    def _on_raise_clicked(self) -> None:
        if ActionType.RAISE in self._legal:
            self._emit(ActionType.RAISE, amount=self.amount_spin.value())
        else:
            self._emit(ActionType.ALL_IN)

    def _emit(self, action_type: ActionType, amount: int | None = None) -> None:
        self.action_chosen.emit(Action(type=action_type, amount=amount))
