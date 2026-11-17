"""The bankroll in the app: menu, setup screens, games and Bankroll screen."""

import random
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from backend.application.bankroll import DEFAULT_BALANCE, GameMode, TransactionType
from backend.application.profile import ProfileStore
from backend.application.setup import (
    DEFAULT_SPIN_BUY_IN,
    DEFAULT_TOURNAMENT_BUY_IN,
    SPIN_BUY_INS,
    TOURNAMENT_BUY_INS,
)
from backend.poker_engine.actions import Action
from backend.poker_engine.betting import get_legal_actions
from backend.poker_engine.constants import ActionType
from backend.simulation.config import SeatSpec, SimulationConfig
from frontend.ui.main_window import MainWindow
from frontend.ui.tournament_screen import TournamentScreen


@pytest.fixture
def store(tmp_path: Path) -> ProfileStore:
    return ProfileStore(tmp_path / "profile.json")


@pytest.fixture
def window(qapp: QApplication, store: ProfileStore) -> Iterator[MainWindow]:
    window = MainWindow(save_sessions=False, rng=random.Random(5), profile=store)
    yield window
    window.close()


def on_page(screen: TournamentScreen) -> bool:
    """True between hands, when the tournament's buttons are shown."""
    return screen.bottom_stack.currentWidget() is screen.tournament_page


def shove(screen: TournamentScreen) -> ActionType:
    """All-in if possible, else call, else check."""
    game = screen.game
    assert game is not None and game.hand is not None
    hand = game.hand
    assert hand.current_player is not None
    legal = {a.type for a in get_legal_actions(hand.current_player, hand)}
    choices = (ActionType.ALL_IN, ActionType.CALL, ActionType.CHECK)

    return next(choice for choice in choices if choice in legal)


def play_to_the_end(screen: TournamentScreen) -> None:
    """The human shoves every hand; keep going until the results open."""
    screen.step_delay_ms = 0
    deadline = time.monotonic() + 60

    while not screen.tournament.is_finished or not screen.results_button.isHidden():
        if time.monotonic() > deadline:
            raise AssertionError("The tournament never finished.")

        game = screen.game

        if screen.is_revealing:
            screen.finish_reveal()
        elif game is not None and game.is_waiting_for_human:
            screen.action_panel.action_chosen.emit(Action(type=shove(screen)))
        elif not on_page(screen):
            pass
        elif not screen.results_button.isHidden():
            screen.results_button.click()
            return
        elif not screen.skip_button.isHidden():
            screen.skip_button.click()
            return
        elif not screen.continue_button.isHidden():
            screen.continue_button.click()

        QTest.qWait(1)


def test_the_menu_shows_the_balance(window: MainWindow, store: ProfileStore) -> None:
    assert window.main_menu.balance_label.text() == "Bankroll  100 000"
    assert window.main_menu.reload_button.isHidden()

    store.bankroll.set_balance(500)
    window.refresh_bankroll()
    assert window.main_menu.balance_label.text() == "Bankroll  500"
    assert not window.main_menu.reload_button.isHidden()

    window.main_menu.reload_button.click()
    assert store.bankroll.balance == DEFAULT_BALANCE
    assert window.main_menu.reload_button.isHidden()
    assert ProfileStore(store.path).bankroll.balance == DEFAULT_BALANCE, "saved"


def test_the_buy_in_presets_and_defaults(window: MainWindow) -> None:
    assert TOURNAMENT_BUY_INS == (100, 500, 1000, 5000, 10_000)
    assert SPIN_BUY_INS == (100, 500, 1000, 5000)
    assert DEFAULT_TOURNAMENT_BUY_IN == DEFAULT_SPIN_BUY_IN == 1000

    choice = window.tournament_setup_screen.buy_in_choice
    assert choice.value() == 1000
    choice.combo.activated.emit(choice.combo.findData(5000))
    assert choice.value() == 5000

    choice.spin.setValue(0)  # A freeroll.
    assert choice.combo.currentText() == "Custom"
    assert window.tournament_setup_screen.current_settings().buy_in == 0


def test_a_mode_the_bankroll_cannot_pay_is_blocked(
    window: MainWindow, store: ProfileStore
) -> None:
    store.bankroll.set_balance(900)
    window.refresh_bankroll()
    cash = window.cash_setup_screen

    assert cash.cost() == 1000
    assert not cash.play_button.isEnabled()
    assert "Not enough money" in cash.buy_in_info.text()
    assert "Bankroll 900" in cash.buy_in_info.text()

    cash.stack_spin.setValue(900)
    assert cash.play_button.isEnabled()
    assert not window.spin_setup_screen.start_button.isEnabled()  # 1 000.

    window.spin_setup_screen.buy_in_spin.setValue(100)
    assert window.spin_setup_screen.start_button.isEnabled()


def test_a_large_buy_in_shows_a_soft_hint(window: MainWindow) -> None:
    window.tournament_setup_screen.buy_in_spin.setValue(10_000)

    assert window.tournament_setup_screen.buy_in_info.state == "hint"
    assert window.tournament_setup_screen.start_button.isEnabled()


def test_a_cash_session_pays_its_buy_in_and_cashes_out(
    window: MainWindow, store: ProfileStore
) -> None:
    window.main_menu.card("cash").click()
    window.cash_setup_screen.play_button.click()
    assert store.bankroll.balance == 99_000
    assert store.bankroll.open_game is not None

    hero = window.game_screen._human_player()  # noqa: SLF001
    stack_behind = hero.stack
    assert store.bankroll.open_game.stack == stack_behind, "saved while playing"

    window.game_screen.menu_button.click()

    assert window.current_screen is window.cash_setup_screen
    assert store.bankroll.balance == 99_000 + stack_behind
    assert store.bankroll.transactions[-1].type == TransactionType.CASH_OUT
    assert store.bankroll.open_game is None
    assert window.main_menu.balance_label.text().endswith(
        f"{99_000 + stack_behind:,}".replace(",", " ")
    )


def test_a_crashed_cash_session_is_cashed_out_at_the_next_launch(
    qapp: QApplication, store: ProfileStore
) -> None:
    window = MainWindow(save_sessions=False, profile=store)
    window.start_game(window.cash_setup_screen.current_settings())
    stack = window.game_screen._human_player().stack  # noqa: SLF001
    # The app dies here: no cash-out. (The window is dropped, never closed.)
    window.game_screen.account = None

    relaunched = MainWindow(save_sessions=False, profile=ProfileStore(store.path))

    assert relaunched.profile.bankroll.balance == 99_000 + stack
    assert relaunched.startup_notice is not None
    assert "cashed out" in relaunched.startup_notice
    relaunched.close()
    window.close()


def test_leaving_a_running_tournament_asks_then_forfeits(
    window: MainWindow, store: ProfileStore
) -> None:
    window.main_menu.card("tournament").click()
    window.tournament_setup_screen.start_button.click()
    screen = window.tournament_screen
    asked = []

    screen.confirm_leave = lambda parent: asked.append(1) or False
    screen.menu_button.click()
    assert asked and window.current_screen is screen, "the user stayed"

    screen.confirm_leave = lambda parent: True
    screen.menu_button.click()

    assert window.current_screen is window.main_menu
    assert [(t.type, t.amount) for t in store.bankroll.transactions] == [
        (TransactionType.BUY_IN, -1000),
        (TransactionType.FORFEIT, 0),
    ]
    assert store.bankroll.balance == 99_000


def test_a_spin_and_go_credits_its_prize(
    window: MainWindow, store: ProfileStore
) -> None:
    window.main_menu.card("spin").click()
    window.spin_setup_screen.start_button.click()
    screen = window.tournament_screen
    tournament = screen.tournament
    assert store.bankroll.balance == 99_000

    play_to_the_end(screen)

    prize = tournament.result.finish_of("Hero").prize
    assert store.bankroll.balance == 99_000 + prize
    assert store.bankroll.open_game is None
    assert store.bankroll.net_result(GameMode.SPIN) == prize - 1000


def test_a_tournament_rebuy_is_paid_from_the_bankroll(
    qapp: QApplication, store: ProfileStore
) -> None:
    window = MainWindow(save_sessions=False, rng=random.Random(12), profile=store)
    window.main_menu.card("tournament").click()
    setup = window.tournament_setup_screen
    setup.opponents_spin.setValue(2)
    setup.stack_spin.setValue(200)
    setup.rebuys_check.setChecked(True)
    setup.start_button.click()
    screen = window.tournament_screen
    screen.step_delay_ms = 0
    deadline = time.monotonic() + 60

    while not (on_page(screen) and not screen.tournament_rebuy_button.isHidden()):
        assert time.monotonic() < deadline
        game = screen.game
        assert game is not None

        if game.is_waiting_for_human:
            screen.action_panel.action_chosen.emit(Action(type=shove(screen)))
        elif on_page(screen) and not screen.continue_button.isHidden():
            screen.continue_button.click()

        QTest.qWait(1)

    screen.tournament_rebuy_button.click()

    assert store.bankroll.transactions[-1].type == TransactionType.REBUY
    assert store.bankroll.balance == 98_000
    window.close()


def test_the_bankroll_screen_shows_the_graph_and_the_ledger(
    window: MainWindow, store: ProfileStore
) -> None:
    window.start_game(window.cash_setup_screen.current_settings())
    window.game_screen.menu_button.click()
    window.back()  # Back to the menu.

    window.main_menu.bankroll_button.click()
    screen = window.bankroll_screen

    assert window.current_screen is screen
    assert screen.balance_label.text().startswith("Balance: ")
    assert len(screen.chart.points) == 3  # Start, buy-in, cash-out.
    assert screen.table.rowCount() == 2
    item = screen.table.item(0, 1)
    assert item is not None and item.text() == "Cash-out", "most recent first"

    screen.filter_combo.setCurrentIndex(screen.filter_combo.findText("Spin & Go"))
    assert screen.table.rowCount() == 0


def test_set_and_reset_are_recorded(window: MainWindow, store: ProfileStore) -> None:
    window.open_bankroll()
    screen = window.bankroll_screen

    screen.ask_balance = lambda parent, current: 250_000
    screen.set_button.click()
    assert store.bankroll.balance == 250_000
    assert window.main_menu.balance_label.text() == "Bankroll  250 000"

    screen.confirm_reset = lambda parent: False
    screen.reset_button.click()
    assert store.bankroll.balance == 250_000

    screen.confirm_reset = lambda parent: True
    screen.reset_button.click()
    assert store.bankroll.balance == DEFAULT_BALANCE

    screen.filter_combo.setCurrentIndex(screen.filter_combo.findText("Adjustments"))
    assert screen.table.rowCount() == 2
    assert ProfileStore(store.path).bankroll.balance == DEFAULT_BALANCE

    screen.hints_check.setChecked(False)
    assert not ProfileStore(store.path).settings.bankroll_hints


def test_watching_the_bot_arena_leaves_the_bankroll_alone(
    window: MainWindow, store: ProfileStore
) -> None:
    config = SimulationConfig(seats=(SeatSpec("tag"), SeatSpec("lag")), hands=5, seed=1)
    window.watch_arena(config)

    for _ in range(200):
        window.arena_watch_screen.step()

    window.back()
    assert store.bankroll.balance == DEFAULT_BALANCE
    assert store.bankroll.transactions == []
