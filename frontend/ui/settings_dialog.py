"""The settings window, opened from any screen with the ⚙ button (or Ctrl+,).

Every change applies at once and is saved with the profile; closing the
window returns to the screen it was opened from.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from backend.application.profile import MAX_VOLUME, BotCards, UserSettings
from backend.application.setup import MAX_PLAYER_NAME_LENGTH, check_player_name
from frontend.pacing import DEFAULT_TABLE_SPEED, TABLE_SPEEDS
from frontend.sounds import Sound, SoundPlayer

BOT_CARDS_LABELS = {
    BotCards.SHOWDOWN: "At showdown only (as in a real game)",
    BotCards.HAND_END: "At the end of every hand",
    BotCards.ALWAYS: "Always (to study the bots)",
}
PREVIEW_SOUND = Sound.BET
"""Played when the volume is set, to hear it."""


class SettingsDialog(QDialog):
    """Your name, the sounds and how the tables look."""

    setting_changed = Signal(str, object)
    """The name of a ``UserSettings`` field and its new value."""
    defaults_requested = Signal()

    def __init__(
        self, settings: UserSettings, sounds: SoundPlayer, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setObjectName("settingsDialog")
        self.setMinimumWidth(480)
        self.sounds = sounds
        self._saved_name = settings.player_name

        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(MAX_PLAYER_NAME_LENGTH)
        self.name_edit.editingFinished.connect(self._on_name_edited)
        self.name_error = QLabel()
        self.name_error.setObjectName("errorText")
        self.name_error.hide()
        name_note = QLabel("Used from your next game, and saved with your profile.")
        name_note.setObjectName("hintText")

        self.sound_check = QCheckBox("Sound effects")
        self.sound_check.toggled.connect(self._on_sound_toggled)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, MAX_VOLUME)
        self.volume_slider.setSingleStep(5)
        self.volume_slider.setPageStep(10)
        self.volume_label = QLabel()
        self.volume_label.setMinimumWidth(42)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.sliderReleased.connect(self.play_preview)
        self.turn_alert_check = QCheckBox("A sound when it is your turn")
        self.turn_alert_check.toggled.connect(
            lambda checked: self.setting_changed.emit("turn_alert", checked)
        )

        self.bot_cards_combo = QComboBox()

        for bot_cards, label in BOT_CARDS_LABELS.items():
            self.bot_cards_combo.addItem(label, bot_cards.value)

        self.bot_cards_combo.setToolTip(
            "Only what you see changes: the bots never see your cards or each other's."
        )
        self.bot_cards_combo.activated.connect(
            lambda: self.setting_changed.emit(
                "bot_cards", self.bot_cards_combo.currentData()
            )
        )
        self.speed_combo = QComboBox()

        for speed in TABLE_SPEEDS:
            self.speed_combo.addItem(speed.name, speed.name)

        self.speed_combo.activated.connect(
            lambda: self.setting_changed.emit(
                "table_speed", self.speed_combo.currentData()
            )
        )
        self.auto_next_check = QCheckBox("Deal the next hand on its own")
        self.big_blinds_check = QCheckBox("Show amounts in big blinds")
        self.four_colors_check = QCheckBox("Four-colour deck (♦ blue, ♣ green)")
        self.hints_check = QCheckBox("Bankroll-management hints on setup screens")
        self.to_front_check = QCheckBox(
            "Bring the table where it is your turn to the front"
        )
        self.to_front_check.setToolTip(
            "With several tables open: once you act, the next table waiting "
            "for you comes forward."
        )

        for check, name in (
            (self.auto_next_check, "auto_next_hand"),
            (self.big_blinds_check, "show_in_big_blinds"),
            (self.four_colors_check, "four_color_deck"),
            (self.hints_check, "bankroll_hints"),
            (self.to_front_check, "table_to_front"),
        ):
            check.toggled.connect(
                lambda checked, name=name: self.setting_changed.emit(name, checked)
            )

        self.defaults_button = QPushButton("Restore defaults")
        self.defaults_button.setToolTip(
            "Every setting of this window, except your name."
        )
        self.defaults_button.clicked.connect(self.defaults_requested)
        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("primary")
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)

        player = QFormLayout()
        player.addRow("Your name", self.name_edit)
        player.addRow("", self.name_error)
        player.addRow("", name_note)

        volume = QHBoxLayout()
        volume.addWidget(self.volume_slider, stretch=1)
        volume.addWidget(self.volume_label)
        sound = QFormLayout()
        sound.addRow(self.sound_check)
        sound.addRow("Volume", volume)
        sound.addRow(self.turn_alert_check)

        tables = QFormLayout()
        tables.addRow("Bots' cards", self.bot_cards_combo)
        tables.addRow("Table speed", self.speed_combo)
        tables.addRow(self.auto_next_check)
        tables.addRow(self.big_blinds_check)
        tables.addRow(self.four_colors_check)
        tables.addRow(self.hints_check)
        tables.addRow(self.to_front_check)

        buttons = QHBoxLayout()
        buttons.addWidget(self.defaults_button)
        buttons.addStretch()
        buttons.addWidget(self.close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        for title, form in (("Player", player), ("Sound", sound), ("Tables", tables)):
            group = QGroupBox(title)
            group.setLayout(form)
            layout.addWidget(group)

        layout.addLayout(buttons)
        self.show_settings(settings)

    def show_settings(self, settings: UserSettings) -> None:
        """Show the values, without emitting any change."""
        self._saved_name = settings.player_name
        speed = settings.table_speed or DEFAULT_TABLE_SPEED
        widgets: list[QWidget] = [
            self.name_edit,
            self.sound_check,
            self.volume_slider,
            self.turn_alert_check,
            self.bot_cards_combo,
            self.speed_combo,
            self.auto_next_check,
            self.big_blinds_check,
            self.four_colors_check,
            self.hints_check,
            self.to_front_check,
        ]

        for widget in widgets:
            widget.blockSignals(True)

        self.name_edit.setText(settings.player_name)
        self.sound_check.setChecked(settings.sound_effects)
        self.volume_slider.setValue(settings.sound_volume)
        self.turn_alert_check.setChecked(settings.turn_alert)
        self.bot_cards_combo.setCurrentIndex(
            self.bot_cards_combo.findData(settings.bot_cards)
        )
        self.speed_combo.setCurrentIndex(self.speed_combo.findData(speed))
        self.auto_next_check.setChecked(settings.auto_next_hand)
        self.big_blinds_check.setChecked(settings.show_in_big_blinds)
        self.four_colors_check.setChecked(settings.four_color_deck)
        self.hints_check.setChecked(settings.bankroll_hints)
        self.to_front_check.setChecked(settings.table_to_front)

        for widget in widgets:
            widget.blockSignals(False)

        self._show_volume(settings.sound_volume)
        self._enable_sound_widgets(settings.sound_effects)
        self.name_error.hide()

    def play_preview(self) -> None:
        self.sounds.play(PREVIEW_SOUND)

    def _on_name_edited(self) -> None:
        name = self.name_edit.text().strip()

        try:
            check_player_name(name)
        except ValueError as error:
            self.name_error.setText(str(error))
            self.name_error.show()
            return

        self.name_error.hide()

        if name != self._saved_name:
            self._saved_name = name
            self.setting_changed.emit("player_name", name)

    def _on_sound_toggled(self, enabled: bool) -> None:
        self._enable_sound_widgets(enabled)
        self.setting_changed.emit("sound_effects", enabled)

    def _enable_sound_widgets(self, enabled: bool) -> None:
        self.volume_slider.setEnabled(enabled)
        self.turn_alert_check.setEnabled(enabled)

    def _on_volume_changed(self, value: int) -> None:
        self._show_volume(value)
        self.setting_changed.emit("sound_volume", value)

        if not self.volume_slider.isSliderDown():  # Keys or a click on the bar.
            self.play_preview()

    def _show_volume(self, value: int) -> None:
        self.volume_label.setText(f"{value}%")

    def done(self, result: int) -> None:
        """A name left invalid is not kept: the saved one comes back."""
        self._on_name_edited()
        self.name_edit.setText(self._saved_name)
        super().done(result)
