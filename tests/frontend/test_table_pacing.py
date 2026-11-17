"""The table's pace: the clock's own timer, auto next hand and the speed.

These tests run the real event loop: the timers must actually fire (an
earlier bug left the action clock's bar frozen in tournaments, because its
timer was replaced by another one of the same name).
"""

import random
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from backend.application.action_clock import ClockPreset
from backend.application.controllers import (
    DecisionContext,
    HumanController,
    PlayerController,
)
from backend.application.game import PokerGame
from backend.application.game_modes import GameMode
from backend.application.profile import ProfileStore
from backend.application.setup import SpinSettings, create_spin_and_go
from backend.poker_engine.actions import Action
from backend.poker_engine.constants import ActionType
from backend.poker_engine.session import GameConfig, create_session
from frontend.pacing import DEFAULT_TABLE_SPEED, TABLE_SPEEDS, table_speed
from frontend.ui.game_screen import GameScreen
from frontend.ui.main_window import MainWindow
from frontend.ui.tournament_screen import TournamentScreen

HUMAN = "Hero"
CLOCK = ClockPreset("Test", 10, 20, top_up=5, top_up_every_hands=25, max_time_bank=40)


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Checker(PlayerController):
    def choose_action(self, context: DecisionContext) -> Action:
        legal = {action.type for action in context.legal_actions}
        can_check = ActionType.CHECK in legal

        return Action(type=ActionType.CHECK if can_check else ActionType.CALL)


def wait_until(condition: Callable[[], bool], seconds: float = 10) -> None:
    deadline = time.monotonic() + seconds

    while not condition():
        assert time.monotonic() < deadline, "the expected state was never reached"
        QTest.qWait(10)


def cash_table(dealer_index: int = 0) -> tuple[GameScreen, PokerGame]:
    """Hero, Bot1 and Bot2; fast steps and a short pause between hands."""
    session = create_session(
        [HUMAN, "Bot1", "Bot2"],
        GameConfig(starting_stack=500, rebuy_stack=500, small_blind=5, big_blind=10),
    )
    session.table.dealer_index = dealer_index
    game = PokerGame(
        session, {HUMAN: HumanController(), "Bot1": Checker(), "Bot2": Checker()}
    )
    screen = GameScreen()
    screen.step_delay_ms = 1
    screen.hand_pause_ms = 50

    return screen, game


# --- The action clock's own timer ------------------------------------------------


def test_the_clock_bar_runs_down_by_itself_in_a_cash_game(qapp: QApplication) -> None:
    fake = FakeTime()
    screen, game = cash_table()
    screen.clock_time_source = fake
    screen.start_game(game, HUMAN, clock=CLOCK)
    assert screen.clock_bar.format() == "10 s"

    fake.now = 4
    QTest.qWait(250)  # The bar's timer ticks every 100 ms.

    assert screen.clock_bar.format() == "6 s"
    assert screen.clock_bar.value() == 600

    fake.now = 30
    wait_until(lambda: game.session.players[0].folded)  # Timed out.


def test_the_clock_bar_runs_down_by_itself_in_a_spin_and_go(
    qapp: QApplication,
) -> None:
    fake = FakeTime()
    screen = TournamentScreen()
    screen.clock_time_source = fake
    tournament = create_spin_and_go(SpinSettings(), HumanController(), random.Random(3))
    screen.start_tournament(tournament, HUMAN, clock=CLOCK)
    screen.step_delay_ms = 1
    screen.finish_reveal()
    wait_until(lambda: tournament.is_waiting_for_human)
    assert screen.clock_bar.format() == "10 s"

    fake.now = 15
    QTest.qWait(250)

    assert screen.clock_bar.format() == "Time bank  15 s"

    hand = tournament.hand
    assert hand is not None
    fake.now = 31
    wait_until(lambda: bool(hand.timed_out_actions))


# --- Auto next hand ----------------------------------------------------------------


def test_the_next_hand_starts_on_its_own(qapp: QApplication) -> None:
    screen, game = cash_table()
    screen.start_game(game, HUMAN)
    first = game.hand

    screen.action_panel.fold_button.click()
    wait_until(lambda: first is not None and first.finished)
    assert screen.bottom_stack.currentIndex() == 1, "the result is shown first"

    wait_until(lambda: game.hand is not first)

    assert game.session.hand_number == 2
    screen.stop()


def test_without_auto_next_hand_the_table_waits(qapp: QApplication) -> None:
    screen, game = cash_table()
    screen.set_auto_next_hand(False)
    screen.start_game(game, HUMAN)

    screen.action_panel.fold_button.click()
    wait_until(lambda: game.hand is not None and game.hand.finished)
    QTest.qWait(200)
    assert game.session.hand_number == 1

    screen.auto_next_check.setChecked(True)  # Switching it on deals now.
    wait_until(lambda: game.session.hand_number == 2)

    screen.next_hand_button.click()  # A late click changes nothing.
    assert game.session.hand_number == 2
    screen.stop()


def test_pause_holds_the_next_hand(qapp: QApplication) -> None:
    screen, game = cash_table()
    screen.start_game(game, HUMAN)
    screen.action_panel.fold_button.click()
    wait_until(lambda: game.hand is not None and game.hand.finished)

    screen.toggle_pause()
    QTest.qWait(200)
    assert game.session.hand_number == 1

    screen.toggle_pause()
    wait_until(lambda: game.session.hand_number == 2)
    screen.stop()


class Shover(PlayerController):
    def choose_action(self, context: DecisionContext) -> Action:
        return Action(type=ActionType.ALL_IN)


def call_a_shove(seed: int) -> tuple[GameScreen, PokerGame]:
    """Heads-up, Hero limps and calls the Bot's shove; the deal is seeded."""
    random.seed(seed)
    session = create_session(
        [HUMAN, "Bot"],
        GameConfig(starting_stack=100, rebuy_stack=100, small_blind=5, big_blind=10),
    )
    session.table.dealer_index = 0  # Hero: button, acts first.
    game = PokerGame(session, {HUMAN: HumanController(), "Bot": Shover()})
    screen = GameScreen()
    screen.step_delay_ms = 1
    screen.hand_pause_ms = 50
    screen.start_game(game, HUMAN)
    hand = game.hand
    assert hand is not None

    screen.action_panel.call_button.click()  # Limp; the Bot shoves.
    wait_until(lambda: game.is_waiting_for_human or hand.finished)

    if game.is_waiting_for_human:
        screen.action_panel.call_button.click()  # Call the shove.

    wait_until(lambda: hand.finished)

    return screen, game


def test_a_busted_player_is_never_dealt_in_automatically(qapp: QApplication) -> None:
    for seed in range(50):  # Find a seeded deal where Hero busts.
        screen, game = call_a_shove(seed)

        if game.session.players[0].is_busted:
            break

        screen.stop()
    else:
        raise AssertionError("Hero never busted.")

    QTest.qWait(200)

    assert game.session.hand_number == 1, "the rebuy is the user's choice"
    assert not screen.rebuy_button.isHidden()
    screen.stop()


# --- Speed --------------------------------------------------------------------------


def test_the_speeds_and_their_default() -> None:
    assert [s.name for s in TABLE_SPEEDS] == ["Slow", "Normal", "Fast", "Turbo"]
    normal = table_speed(DEFAULT_TABLE_SPEED)
    assert (normal.action_delay_ms, normal.hand_pause_ms) == (900, 3000)
    assert table_speed("unknown") == normal
    delays = [s.action_delay_ms for s in TABLE_SPEEDS]
    assert delays == sorted(delays, reverse=True)


def test_the_speed_is_shared_and_remembered(qapp: QApplication, tmp_path: Path) -> None:
    path = tmp_path / "profile.json"
    window = MainWindow(save_sessions=False, profile=ProfileStore(path))
    screen = window.open_game_window(GameMode.CASH).table_screen
    tournament = window.open_game_window(GameMode.TOURNAMENT).table_screen
    assert screen.speed == "Normal" and screen.step_delay_ms == 900

    screen.speed_combo.activated.emit(screen.speed_combo.findData("Turbo"))
    tournament.auto_next_check.setChecked(False)

    assert screen.step_delay_ms == 150 and screen.hand_pause_ms == 600
    assert tournament.speed == "Turbo"
    assert not screen.auto_next_hand
    window.close()

    reopened = MainWindow(save_sessions=False, profile=ProfileStore(path))
    assert reopened.open_game_window(GameMode.TOURNAMENT).table_screen.speed == "Turbo"
    cash = reopened.open_game_window(GameMode.CASH).table_screen
    assert cash.step_delay_ms == 150
    assert not cash.auto_next_hand
    reopened.close()
