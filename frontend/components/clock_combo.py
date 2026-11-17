"""The choice of the human's action clock, on each setup screen."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QWidget

from backend.application.action_clock import (
    CLOCK_CHOICES,
    CLOCK_PRESETS,
    OFF,
    ClockPreset,
    clock_preset,
)


class ClockCombo(QComboBox):
    """Off or one of the clock presets.

    The mode's default is shown until the user picks a clock themselves;
    ``chosen`` is emitted only for the user's own choices.
    """

    chosen = Signal(str)
    """Emitted with the preset name when the user picks a clock."""

    def __init__(self, default: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.addItem("Off — no time limit", OFF)

        for preset in CLOCK_PRESETS:
            self.addItem(preset.describe(), preset.name)

        self.user_chosen = False
        """True once the user picked a clock (here or in a previous launch)."""
        self.set_choice(default)
        self.activated.connect(self._on_activated)

    def choice(self) -> str:
        return self.currentData()

    def preset(self) -> ClockPreset | None:
        """The chosen preset, or None for "Off"."""
        return clock_preset(self.choice())

    def set_choice(self, name: str, user_chosen: bool = False) -> None:
        """Select a preset by name; unknown names are ignored."""
        if name not in CLOCK_CHOICES:
            return

        self.setCurrentIndex(self.findData(name))
        self.user_chosen = self.user_chosen or user_chosen

    def follow_default(self, name: str) -> None:
        """Show a new default, unless the user picked a clock."""
        if not self.user_chosen:
            self.set_choice(name)

    def _on_activated(self, index: int) -> None:
        self.user_chosen = True
        self.chosen.emit(self.itemData(index))
