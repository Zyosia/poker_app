"""The settings window: opened from any screen, applied at once, saved."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import QApplication

from backend.application.profile import BotCards, ProfileStore
from frontend.components.card_widget import CardWidget
from frontend.sounds import Sound
from frontend.ui.main_window import MainWindow
from frontend.ui.settings_dialog import SettingsDialog
from tests.frontend.test_game_screen import HUMAN, make_game

ProcessUntil = Callable[[Callable[[], bool]], None]


@pytest.fixture
def store(tmp_path: Path) -> ProfileStore:
    return ProfileStore(tmp_path / "profile.json")


@pytest.fixture
def window(qapp: QApplication, store: ProfileStore) -> Iterator[MainWindow]:
    window = MainWindow(save_sessions=False, profile=store)
    window.game_screen.step_delay_ms = 0
    yield window
    CardWidget.four_colors = False  # Shared by every card: back to the default.


def edit_name(dialog: SettingsDialog, name: str) -> None:
    dialog.name_edit.setText(name)
    dialog.name_edit.editingFinished.emit()


def start_cash_game(window: MainWindow, process_until: ProcessUntil) -> None:
    """A table where Hero, the Button, acts first against passive bots."""
    game = make_game(dealer_index=0)
    window.push(window.game_screen)
    window.game_screen.start_game(game, human_name=HUMAN)
    process_until(lambda: game.is_waiting_for_human)


# --- Opening and closing -----------------------------------------------------


def test_the_settings_button_sits_above_every_screen(window: MainWindow) -> None:
    window.show()

    for key in ("cash", "tournament", "spin", "tools", "arena"):
        window.main_menu.card(key).click()
        assert window.settings_button.isVisible()
        assert window.childAt(window.settings_button.geometry().center()) is (
            window.settings_button
        )
        window.back()


def test_closing_the_settings_returns_to_the_same_screen(window: MainWindow) -> None:
    window.main_menu.card("tournament").click()

    window.settings_button.click()
    dialog = window.settings_dialog
    assert dialog is not None and dialog.isModal()
    dialog.close_button.click()

    assert window.settings_dialog is None
    assert window.current_screen is window.tournament_setup_screen


def test_the_settings_open_once_even_when_asked_twice(window: MainWindow) -> None:
    first = window.open_settings()

    assert window.open_settings() is first


def test_the_table_waits_while_the_settings_are_open(
    window: MainWindow, process_until: ProcessUntil
) -> None:
    start_cash_game(window, process_until)
    screen = window.game_screen

    dialog = window.open_settings()
    assert screen.paused
    assert not screen.action_panel.fold_button.isEnabled()

    dialog.close_button.click()
    assert not screen.paused
    assert screen.action_panel.fold_button.isEnabled()


def test_a_table_you_paused_stays_paused(
    window: MainWindow, process_until: ProcessUntil
) -> None:
    start_cash_game(window, process_until)
    screen = window.game_screen
    screen.toggle_pause()

    window.open_settings().close_button.click()

    assert screen.paused


# --- Your name ---------------------------------------------------------------


def test_your_name_is_used_by_every_mode_and_kept(
    window: MainWindow, store: ProfileStore
) -> None:
    edit_name(window.open_settings(), "Nael")

    assert window.cash_setup_screen.name_label.text() == "Nael"
    assert window.tournament_setup_screen.current_settings().player_name == "Nael"
    assert window.spin_setup_screen.current_settings().player_name == "Nael"
    assert ProfileStore(store.path).settings.player_name == "Nael"

    assert window.settings_dialog is not None
    window.settings_dialog.close_button.click()
    window.main_menu.card("cash").click()
    window.cash_setup_screen.play_button.click()
    game = window.game_screen.game
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
    dialog = window.open_settings()

    dialog.volume_slider.setValue(40)
    assert window.sounds.volume == pytest.approx(0.4)
    assert dialog.volume_label.text() == "40%"
    assert window.sounds.recent[-1] == Sound.BET  # A preview of the volume.

    dialog.turn_alert_check.setChecked(False)
    assert window.game_screen.turn_alert is False

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


def test_the_table_settings_reach_both_tables(
    window: MainWindow, store: ProfileStore
) -> None:
    dialog = window.open_settings()

    dialog.bot_cards_combo.setCurrentIndex(
        dialog.bot_cards_combo.findData(BotCards.HAND_END.value)
    )
    dialog.bot_cards_combo.activated.emit(dialog.bot_cards_combo.currentIndex())
    dialog.speed_combo.setCurrentIndex(dialog.speed_combo.findData("Turbo"))
    dialog.speed_combo.activated.emit(dialog.speed_combo.currentIndex())
    dialog.big_blinds_check.setChecked(True)
    dialog.auto_next_check.setChecked(False)

    for screen in window.played_screens:
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


def test_a_change_on_the_table_shows_in_the_settings(window: MainWindow) -> None:
    window.game_screen.big_blinds_check.setChecked(True)

    assert window.open_settings().big_blinds_check.isChecked()


def test_restore_defaults_keeps_your_name(
    window: MainWindow, store: ProfileStore
) -> None:
    dialog = window.open_settings()
    edit_name(dialog, "Nael")
    dialog.volume_slider.setValue(10)
    dialog.four_colors_check.setChecked(True)

    dialog.defaults_button.click()

    assert store.settings.player_name == "Nael"
    assert store.settings.sound_volume == 70
    assert store.settings.four_color_deck is False
    assert dialog.volume_slider.value() == 70
    assert not dialog.four_colors_check.isChecked()


def test_the_keyboard_shortcut_opens_the_settings(window: MainWindow) -> None:
    shortcut = window.findChild(QShortcut)
    assert shortcut is not None
    assert shortcut.key().toString() == "Ctrl+,"

    shortcut.activated.emit()

    assert window.settings_dialog is not None
