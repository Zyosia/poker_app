"""The Spin & Go window opens on the buy-ins started in one click (V3.2)."""

import random
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from backend.application.payouts import FAIR_MULTIPLIERS
from backend.application.profile import ProfileStore
from backend.application.setup import (
    LEVELS_BY_TIME,
    QUICK_SPIN_BUY_INS,
    SpinSettings,
)
from backend.bots.factory import Difficulty
from backend.poker_engine.constants import NO_LIMIT
from frontend.ui.game_window import GameWindow
from frontend.ui.main_window import MainWindow
from frontend.ui.spin_quick_screen import SpinQuickScreen
from tests.frontend.windows import open_table, played_setup, tournament_screen


@pytest.fixture
def store(tmp_path: Path) -> ProfileStore:
    return ProfileStore(tmp_path / "profile.json")


@pytest.fixture
def window(qapp: QApplication, store: ProfileStore) -> Iterator[MainWindow]:
    window = MainWindow(save_sessions=False, rng=random.Random(8), profile=store)
    yield window
    window.close()


def quick(table: GameWindow) -> SpinQuickScreen:
    screen = table.quick_screen
    assert screen is not None

    return screen


def test_the_spin_window_opens_on_the_buy_ins(window: MainWindow) -> None:
    table = open_table(window, "spin")
    screen = quick(table)

    assert table.current_screen is screen
    assert list(screen.buy_in_buttons) == list(QUICK_SPIN_BUY_INS)
    assert screen.buy_in_buttons[100_000].text() == "100 000"
    assert screen.difficulty == Difficulty.EASY  # The default.


def test_the_other_modes_have_no_quick_screen(window: MainWindow) -> None:
    for mode in ("cash", "tournament"):
        table = open_table(window, mode)
        assert table.quick_screen is None
        assert table.current_screen is table.setup_screen


def test_a_buy_in_starts_the_spin_at_once(
    window: MainWindow, store: ProfileStore
) -> None:
    table = open_table(window, "spin")
    started: list[SpinSettings] = []
    quick(table).start_requested.connect(started.append)

    quick(table).buy_in_buttons[50].click()

    [settings] = started
    assert (settings.buy_in, settings.betting) == (50, NO_LIMIT)
    assert settings.levels_by == LEVELS_BY_TIME
    assert settings.multipliers == FAIR_MULTIPLIERS

    screen = tournament_screen(table)
    assert table.current_screen is screen
    assert screen.tournament.config.buy_in == 50
    assert screen.tournament.clock is not None  # Levels by time.
    clock = screen.action_clock
    assert clock is not None and clock.preset.name == "Standard"
    assert store.bankroll.balance == 100_000 - 50


def test_the_custom_spin_keeps_its_own_clock(window: MainWindow) -> None:
    table = open_table(window, "spin")
    setup = played_setup(table)
    setup.clock_combo.set_choice("Hyper")

    setup.start_button.click()

    clock = tournament_screen(table).action_clock
    assert clock is not None and clock.preset.name == "Hyper"


def test_the_difficulty_draws_the_two_bots(window: MainWindow) -> None:
    screen = quick(open_table(window, "spin"))
    screen.rng.seed(1)
    screen.set_difficulty(Difficulty.HARD)

    assert screen.difficulty == Difficulty.HARD
    assert "Hard" in screen.difficulty_label.text()

    drawn = {style for _ in range(100) for style in screen.settings_for(10).opponents}
    assert {"shark", "adaptive"} & drawn

    screen.set_difficulty(Difficulty.EASY)
    drawn = {style for _ in range(100) for style in screen.settings_for(10).opponents}
    assert not {"shark", "adaptive"} & drawn


def test_a_buy_in_the_bankroll_cannot_pay_is_disabled(
    window: MainWindow, store: ProfileStore
) -> None:
    store.bankroll.balance = 30
    table = open_table(window, "spin")
    buttons = quick(table).buy_in_buttons

    assert buttons[25].isEnabled()
    assert not buttons[50].isEnabled()
    assert "Not enough money" in buttons[50].toolTip()


def test_custom_opens_the_setup_and_back_returns(window: MainWindow) -> None:
    table = open_table(window, "spin")
    screen = quick(table)

    screen.custom_button.click()
    assert table.current_screen is table.setup_screen

    played_setup(table).back_button.click()
    assert table.current_screen is screen

    screen.back_button.click()
    assert table not in window.game_windows


def test_play_again_draws_two_new_bots_for_the_same_buy_in(
    window: MainWindow, store: ProfileStore
) -> None:
    table = open_table(window, "spin")
    screen = quick(table)
    screen.rng.seed(2)
    screen.buy_in_buttons[20].click()
    first = tournament_screen(table).tournament
    first_bots = {
        name: controller.style
        for name, controller in first.controllers.items()
        if name != "Hero"
    }

    for _ in range(5):  # Until the draw changes the bots (seeded).
        table.play_again()
        again = tournament_screen(table).tournament
        bots = {
            name: controller.style
            for name, controller in again.controllers.items()
            if name != "Hero"
        }

        assert again is not first and again.config.buy_in == 20

        if bots != first_bots:
            break
    else:
        pytest.fail("Play again always seated the same bots.")

    assert store.bankroll.balance < 100_000 - 20


def test_the_player_name_follows_the_settings(window: MainWindow) -> None:
    table = open_table(window, "spin")
    window.save_setting("player_name", "Alice")
    table.apply_settings(window.profile.settings)

    assert quick(table).settings_for(5).player_name == "Alice"
