"""The settings window: opened from any window, applied at once, saved."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QApplication

from backend.application.profile import BotCards, ProfileStore
from frontend.components.card_widget import CardWidget
from frontend.sounds import Sound
from frontend.ui.main_window import MainWindow
from frontend.ui.settings_dialog import SettingsDialog
from tests.frontend.windows import ProcessUntil, cash_setup, open_table, start_test_game


@pytest.fixture
def store(tmp_path: Path) -> ProfileStore:
    return ProfileStore(tmp_path / "profile.json")


@pytest.fixture
def window(qapp: QApplication, store: ProfileStore) -> Iterator[MainWindow]:
    window = MainWindow(save_sessions=False, profile=store)
    yield window
    CardWidget.four_colors = False  # Shared by every card: back to the default.


def edit_name(dialog: SettingsDialog, name: str) -> None:
    dialog.name_edit.setText(name)
    dialog.name_edit.editingFinished.emit()


# --- Opening and closing -----------------------------------------------------


def test_the_settings_button_sits_above_every_screen(window: MainWindow) -> None:
    window.show()

    for key in ("tools", "arena"):
        window.main_menu.card(key).click()
        assert window.childAt(window.settings_button.geometry().center()) is (
            window.settings_button
        )
        window.back()

    for key in ("cash", "tournament", "spin"):
        table = open_table(window, key)
        assert table.settings_button.isVisible()
        assert table.childAt(table.settings_button.geometry().center()) is (
            table.settings_button
        )


def test_the_settings_open_over_the_window_they_were_asked_from(
    window: MainWindow,
) -> None:
    table = open_table(window, "tournament")

    table.settings_button.click()
    dialog = window.settings_dialog
    assert dialog is not None and dialog.isModal()
    assert dialog.parent() is table

    dialog.close_button.click()

    assert window.settings_dialog is None
    assert table.current_screen is table.setup_screen


def test_the_settings_open_once_even_when_asked_twice(window: MainWindow) -> None:
    table = open_table(window, "cash")
    first = window.open_settings()

    table.settings_button.click()

    assert window.open_settings() is first
    assert window.settings_dialog is first


def test_every_table_waits_while_the_settings_are_open(
    window: MainWindow, process_until: ProcessUntil
) -> None:
    screens = []

    for _ in range(2):
        table = open_table(window, "cash")
        start_test_game(table, process_until)
        screens.append(table.table_screen)

    dialog = window.open_settings()
    assert all(screen.paused for screen in screens)
    assert not screens[0].action_panel.fold_button.isEnabled()

    dialog.close_button.click()
    assert not any(screen.paused for screen in screens)
    assert screens[0].action_panel.fold_button.isEnabled()


def test_a_table_you_paused_stays_paused(
    window: MainWindow, process_until: ProcessUntil
) -> None:
    table = open_table(window, "cash")
    start_test_game(table, process_until)
    table.table_screen.toggle_pause()

    window.open_settings().close_button.click()

    assert table.table_screen.paused


# --- Your name ---------------------------------------------------------------


def test_your_name_is_used_by_every_mode_and_kept(
    window: MainWindow, store: ProfileStore
) -> None:
    cash = open_table(window, "cash")
    tournament = open_table(window, "tournament")
    edit_name(window.open_settings(), "Nael")

    assert cash.setup_screen.name_label.text() == "Nael"
    assert tournament.setup_screen.current_settings().player_name == "Nael"
    assert open_table(window, "spin").setup_screen.current_settings().player_name == (
        "Nael"
    )
    assert ProfileStore(store.path).settings.player_name == "Nael"

    assert window.settings_dialog is not None
    window.settings_dialog.close_button.click()
    cash_setup(cash).play_button.click()
    game = cash.table_screen.game
    assert game is not None
    assert "Nael" in game.controllers


def test_an_invalid_name_is_refused_and_the_saved_one_kept(
    window: MainWindow, store: ProfileStore
) -> None:
    dialog = window.open_settings()
    edit_name(dialog, "   ")

    assert dialog.name_error.isVisibleTo(dialog)
    assert "empty" in dialog.name_error.text()
    assert store.settings.player_name == "Hero"

    dialog.close_button.click()
    assert dialog.name_edit.text() == "Hero"


# --- Sound -------------------------------------------------------------------


def test_the_sound_settings_apply_at_once_and_are_kept(
    window: MainWindow, store: ProfileStore
) -> None:
    table = open_table(window, "cash")
    dialog = window.open_settings()

    dialog.volume_slider.setValue(40)
    assert window.sounds.volume == pytest.approx(0.4)
    assert dialog.volume_label.text() == "40%"
    assert window.sounds.recent[-1] == Sound.BET  # A preview of the volume.

    dialog.turn_alert_check.setChecked(False)
    assert table.table_screen.turn_alert is False

    dialog.sound_check.setChecked(False)
    assert window.sounds.enabled is False
    assert not dialog.volume_slider.isEnabled()

    saved = ProfileStore(store.path).settings
    assert (saved.sound_volume, saved.turn_alert, saved.sound_effects) == (
        40,
        False,
        False,
    )


def test_the_saved_sound_settings_are_applied_at_launch(store: ProfileStore) -> None:
    store.settings.sound_effects = False
    store.settings.sound_volume = 25
    store.save()

    window = MainWindow(save_sessions=False, profile=ProfileStore(store.path))

    assert window.sounds.enabled is False
    assert window.sounds.volume == pytest.approx(0.25)


# --- Tables ------------------------------------------------------------------


def test_the_table_settings_reach_every_table(
    window: MainWindow, store: ProfileStore
) -> None:
    tables = [open_table(window, "cash"), open_table(window, "tournament")]
    dialog = window.open_settings()

    dialog.bot_cards_combo.setCurrentIndex(
        dialog.bot_cards_combo.findData(BotCards.HAND_END.value)
    )
    dialog.bot_cards_combo.activated.emit(dialog.bot_cards_combo.currentIndex())
    dialog.speed_combo.setCurrentIndex(dialog.speed_combo.findData("Turbo"))
    dialog.speed_combo.activated.emit(dialog.speed_combo.currentIndex())
    dialog.big_blinds_check.setChecked(True)
    dialog.auto_next_check.setChecked(False)

    for table in [*tables, open_table(window, "spin")]:  # Opened later too.
        screen = table.table_screen
        assert screen.bot_cards == BotCards.HAND_END
        assert screen.speed == "Turbo"
        assert screen.show_in_big_blinds
        assert not screen.auto_next_hand

    assert window.replayer_screen.show_in_big_blinds
    saved = ProfileStore(store.path).settings
    assert saved.bot_cards == BotCards.HAND_END
    assert saved.table_speed == "Turbo"


def test_the_four_colour_deck_paints_diamonds_blue(window: MainWindow) -> None:
    dialog = window.open_settings()
    dialog.four_colors_check.setChecked(True)

    assert CardWidget.four_colors is True


def test_a_change_at_one_table_reaches_the_others_and_the_settings(
    window: MainWindow,
) -> None:
    first = open_table(window, "cash")
    second = open_table(window, "tournament")

    first.table_screen.big_blinds_check.setChecked(True)

    assert second.table_screen.show_in_big_blinds
    assert window.open_settings().big_blinds_check.isChecked()


def test_bringing_the_table_to_the_front_can_be_turned_off(
    window: MainWindow, store: ProfileStore
) -> None:
    dialog = window.open_settings()
    assert dialog.to_front_check.isChecked()

    dialog.to_front_check.setChecked(False)

    assert ProfileStore(store.path).settings.table_to_front is False


def test_restore_defaults_keeps_your_name(
    window: MainWindow, store: ProfileStore
) -> None:
    dialog = window.open_settings()
    edit_name(dialog, "Nael")
    dialog.volume_slider.setValue(10)
    dialog.four_colors_check.setChecked(True)
    dialog.to_front_check.setChecked(False)

    dialog.defaults_button.click()

    assert store.settings.player_name == "Nael"
    assert store.settings.sound_volume == 70
    assert store.settings.four_color_deck is False
    assert store.settings.table_to_front is True
    assert dialog.volume_slider.value() == 70
    assert not dialog.four_colors_check.isChecked()


def test_the_keyboard_shortcut_opens_the_settings_from_any_window(
    window: MainWindow,
) -> None:
    table = open_table(window, "cash")

    for target in (window, table):
        shortcut = target.findChild(QShortcut)
        assert shortcut is not None
        assert shortcut.key().toString() == "Ctrl+,"

        shortcut.activated.emit()

        dialog = window.settings_dialog
        assert dialog is not None and dialog.parent() is target
        dialog.close_button.click()
