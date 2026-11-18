"""V3.0 at the table: buy-in limits, top-ups, bots rebuying, the straddle."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from backend.application.bankroll import TransactionType
from backend.application.game import PokerGame
from backend.application.profile import ProfileStore
from frontend.ui.cash_setup_screen import CashSetupScreen
from frontend.ui.game_screen import GameScreen
from frontend.ui.game_window import GameWindow
from frontend.ui.main_window import MainWindow
from tests.frontend.windows import ProcessUntil, cash_setup, open_table


@pytest.fixture
def window(qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    window = MainWindow(save_sessions=False, profile=ProfileStore(tmp_path / "p.json"))
    yield window
    window.close()


def test_the_buy_in_is_40_to_100_big_blinds_and_follows_the_blinds(
    qapp: QApplication,
) -> None:
    setup = CashSetupScreen()

    assert (setup.stack_spin.minimum(), setup.stack_spin.maximum()) == (400, 1000)
    assert setup.stack_spin.value() == 1000

    setup.stack_spin.setValue(600)  # 60 big blinds...
    setup.blinds_combo.setCurrentIndex(1)  # ...at 10/20 too.

    assert (setup.stack_spin.minimum(), setup.stack_spin.maximum()) == (800, 2000)
    assert setup.stack_spin.value() == 1200


def test_the_table_options_reach_the_settings(qapp: QApplication) -> None:
    setup = CashSetupScreen()
    defaults = setup.current_settings()
    assert (defaults.straddle, defaults.bots_rebuy, defaults.auto_top_up) == (
        False,
        True,
        False,
    )

    setup.straddle_check.setChecked(True)
    setup.bots_rebuy_check.setChecked(False)
    setup.auto_top_up_check.setChecked(True)
    chosen = setup.current_settings()

    assert (chosen.straddle, chosen.bots_rebuy, chosen.auto_top_up) == (
        True,
        False,
        True,
    )


def play_one_hand(
    window: MainWindow, process_until: ProcessUntil, **options: bool
) -> tuple[GameWindow, GameScreen, PokerGame]:
    """Start a cash game at 5/10 with 600 chips; fold the first hand."""
    table = open_table(window, "cash")
    setup = cash_setup(table)
    setup.opponents_spin.setValue(2)
    setup.stack_spin.setValue(600)

    for name, checked in options.items():
        getattr(setup, f"{name}_check").setChecked(checked)

    setup.play_button.click()
    screen = table.table_screen
    screen.auto_next_check.setChecked(False)
    game = screen.game
    assert isinstance(game, PokerGame)

    def hand_over() -> bool:
        if game.is_waiting_for_human:
            screen.action_panel.fold_button.click()
        return not game.is_hand_in_progress

    process_until(hand_over)

    return table, screen, game


def test_top_up_between_hands(window: MainWindow, process_until: ProcessUntil) -> None:
    _, screen, game = play_one_hand(window, process_until)
    hero = next(p for p in game.session.players if p.name == screen.human_name)
    balance = window.profile.bankroll.balance
    missing = 1000 - hero.stack

    assert screen.top_up_button.isVisibleTo(screen)
    assert screen.top_up_button.text().replace(" ", "") == f"Topup+{missing}"

    assert screen.top_up() == missing
    assert hero.stack == 1000
    assert window.profile.bankroll.balance == balance - missing
    last = window.profile.bankroll.transactions[-1]
    assert last.type == TransactionType.TOP_UP and last.amount == -missing
    assert not screen.top_up_button.isVisibleTo(screen)
    assert "tops up" in screen.history_view.text()


def test_auto_top_up_before_every_hand(
    window: MainWindow, process_until: ProcessUntil
) -> None:
    _, screen, game = play_one_hand(window, process_until, auto_top_up=True)
    hero = next(p for p in game.session.players if p.name == screen.human_name)

    # The stack went back to the maximum before each hand was dealt.
    first = game.session.hands[0]
    assert next(s.stack for s in first.seats if s.name == hero.name) == 1000
    screen.next_hand_button.click()

    second = game.session.hands[1]
    assert next(s.stack for s in second.seats if s.name == hero.name) == 1000


def test_a_straddled_table_shows_the_straddle(
    window: MainWindow, process_until: ProcessUntil
) -> None:
    _, screen, game = play_one_hand(window, process_until, straddle=True)

    assert any(e.action == "post_straddle" for e in game.session.hands[0].actions)
    assert "straddles 20" in screen.history_view.text()


def test_busted_bots_rebuy_in_the_history(
    window: MainWindow, process_until: ProcessUntil
) -> None:
    _, screen, game = play_one_hand(window, process_until)
    bot = next(p for p in game.session.players if p.name != screen.human_name)
    bot.stack = 0
    game._on_hand_finished()  # noqa: SLF001 - as if the bot had just busted
    screen._show_hand_result(game.session.hands[-1])  # noqa: SLF001

    assert bot.stack == 1000
    assert f"{bot.name} rebuys 1000" in screen.history_view.text()
