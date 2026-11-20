"""The bots' play styles at the table, on demand (V3.2)."""

import random
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from backend.application.controllers import HumanController, PlayerController
from backend.application.profile import ProfileStore, UserSettings
from backend.application.setup import GameSettings, create_game
from backend.bots.factory import create_bot
from frontend.components.seat_widget import SEAT_SIZE, SeatState, SeatWidget
from frontend.sounds import SoundPlayer
from frontend.ui.game_screen import GameScreen, bot_styles, build_table_state
from frontend.ui.main_window import MainWindow
from frontend.ui.settings_dialog import SettingsDialog
from tests.frontend.test_game_screen import PassiveBot
from tests.frontend.test_live_tables_ui import play_others, wait_for_your_turn
from tests.frontend.test_multi_table_ui import start_multi_table
from tests.frontend.windows import ProcessUntil, cash_setup, open_table


@pytest.fixture
def window(qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    window = MainWindow(
        save_sessions=False,
        rng=random.Random(3),
        profile=ProfileStore(tmp_path / "profile.json"),
    )
    yield window
    window.close()


def seat(state: SeatState) -> SeatWidget:
    widget = SeatWidget()
    widget.set_state(state)

    return widget


def test_the_styles_are_the_labels_of_the_bots_only() -> None:
    controllers: dict[str, PlayerController] = {
        "Hero": HumanController(),
        "Ann": create_bot("station", random.Random(0)),
        "Bob": create_bot("shark", random.Random(0)),
        "Tester": PassiveBot(),  # A controller made without a style.
    }

    assert bot_styles(controllers) == {"Ann": "Calling Station", "Bob": "Shark"}


def test_the_table_state_shows_the_styles_given() -> None:
    game = create_game(GameSettings(opponents=("nit", "lag")), HumanController())
    hand = game.start_hand()

    shown = build_table_state(hand, "Hero", styles=bot_styles(game.controllers)).seats
    hidden = build_table_state(hand, "Hero").seats

    assert [seat.style for seat in shown] == ["", "Nit", "LAG"]
    assert all(seat.style == "" for seat in hidden)


def test_a_seat_grows_by_one_line_for_the_style(qapp: QApplication) -> None:
    state = SeatState(name="Ann", stack=100, cards=(), cards_face_up=False, status="")
    widget = seat(state)
    assert widget.height() == SEAT_SIZE.height()
    assert widget.style_label.isHidden()

    widget.set_state(SeatState("Ann", 100, (), False, "", style="TAG"))
    assert widget.style_label.text() == "TAG"
    assert not widget.style_label.isHidden()
    assert widget.height() > SEAT_SIZE.height()

    widget.set_scale(0.7)
    shrunk = widget.height()
    widget.set_state(state)
    assert widget.height() < shrunk


def test_the_styles_are_hidden_by_default_and_shown_on_demand(
    window: MainWindow, process_until: ProcessUntil
) -> None:
    assert UserSettings().show_bot_styles is False
    table = open_table(window, "cash")
    setup = cash_setup(table)
    setup.play_button.click()
    screen = table.table_screen
    game = screen.game
    assert game is not None
    process_until(lambda: game.hand is not None)

    def styles() -> list[str]:
        return [seat.style for seat in screen.table_widget.state.seats]

    assert not screen.styles_check.isChecked()
    assert set(styles()) == {""}

    screen.styles_check.click()

    assert styles()[0] == ""  # Your own seat.
    assert all(styles()[1:])
    assert window.profile.settings.show_bot_styles  # Remembered.

    screen.styles_check.click()
    assert set(styles()) == {""}
    assert not window.profile.settings.show_bot_styles


def test_every_table_follows_the_choice(window: MainWindow) -> None:
    first = open_table(window, "cash")
    second = open_table(window, "tournament")

    first.table_screen.styles_check.click()

    assert second.table_screen.show_bot_styles
    assert window.profile.settings.show_bot_styles


def test_the_settings_window_switches_the_styles(window: MainWindow) -> None:
    table = open_table(window, "cash")
    dialog = window.open_settings()

    dialog.styles_check.click()

    assert window.profile.settings.show_bot_styles
    assert table.table_screen.show_bot_styles

    window.restore_default_settings()
    assert not window.profile.settings.show_bot_styles
    assert not dialog.styles_check.isChecked()
    dialog.close()


def test_the_settings_window_shows_the_saved_choice(qapp: QApplication) -> None:
    settings = UserSettings(show_bot_styles=True)
    dialog = SettingsDialog(settings, SoundPlayer())

    assert dialog.styles_check.isChecked()


def test_the_choice_survives_a_restart(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profile.json")
    store.settings.show_bot_styles = True
    store.save()

    assert ProfileStore(tmp_path / "profile.json").settings.show_bot_styles


def test_a_watched_table_shows_the_styles_too(
    qapp: QApplication, window: MainWindow
) -> None:
    screen = start_multi_table(window)
    table_window = window.game_windows[-1]
    screen.styles_check.click()
    wait_for_your_turn(qapp, screen)
    spectator = table_window.watch_table(2)
    assert spectator is not None
    play_others(screen, looks=20)
    seats = spectator.table_widget.state.seats

    assert seats and all(seat.style for seat in seats)


def test_a_game_screen_without_a_game_shows_no_style(qapp: QApplication) -> None:
    screen = GameScreen()
    screen.set_show_bot_styles(True)

    assert screen.table_styles() == {}
