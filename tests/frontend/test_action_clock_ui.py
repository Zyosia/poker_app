"""The action clock on the table: bar, time bank, timeouts and Pause."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from backend.application.action_clock import ClockPreset, clock_preset
from backend.application.controllers import (
    DecisionContext,
    HumanController,
    PlayerController,
)
from backend.application.game import PokerGame
from backend.application.profile import ProfileStore
from backend.poker_engine.actions import Action
from backend.poker_engine.constants import ActionType
from backend.poker_engine.session import GameConfig, create_session
from frontend.ui.game_screen import GameScreen
from frontend.ui.main_window import MainWindow

HUMAN = "Hero"
QUICK = ClockPreset("Quick", 10, 20, top_up=5, top_up_every_hands=1, max_time_bank=40)


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Checker(PlayerController):
    def choose_action(self, context: DecisionContext) -> Action:
        legal = {action.type for action in context.legal_actions}

        return Action(
            type=ActionType.CHECK if ActionType.CHECK in legal else ActionType.CALL
        )


def make_game(dealer_index: int) -> PokerGame:
    session = create_session(
        [HUMAN, "Bot1", "Bot2"],
        GameConfig(starting_stack=500, rebuy_stack=500, small_blind=5, big_blind=10),
    )
    session.table.dealer_index = dealer_index

    return PokerGame(
        session, {HUMAN: HumanController(), "Bot1": Checker(), "Bot2": Checker()}
    )


@pytest.fixture
def fake_time() -> FakeTime:
    return FakeTime()


def start(fake_time: FakeTime, dealer_index: int, clock: ClockPreset = QUICK):
    screen = GameScreen()
    screen.step_delay_ms = 0
    screen.clock_time_source = fake_time
    game = make_game(dealer_index)
    screen.start_game(game, human_name=HUMAN, clock=clock)

    return screen, game


def tick(screen: GameScreen) -> None:
    screen._on_clock_tick()  # noqa: SLF001 - the 100 ms timer, run by hand


def play_bots(screen: GameScreen, qapp: QApplication) -> None:
    game = screen.game
    assert game is not None

    for _ in range(100):
        if game.is_waiting_for_human or not game.is_hand_in_progress:
            return

        screen._play_step()  # noqa: SLF001

    raise AssertionError("The bots never handed the action back.")


def test_the_bar_runs_down_then_shows_the_time_bank(
    qapp: QApplication, fake_time: FakeTime
) -> None:
    screen, game = start(fake_time, dealer_index=0)  # Hero acts first.
    bar = screen.clock_bar
    assert game.is_waiting_for_human
    assert not bar.isHidden()
    assert bar.format() == "10 s"
    assert bar.property("state") == "normal"

    fake_time.now = 6
    tick(screen)
    assert bar.format() == "4 s"
    assert bar.property("state") == "warning", "last 5 seconds"

    fake_time.now = 15
    tick(screen)
    assert bar.format() == "Time bank  15 s"
    assert bar.property("state") == "bank"
    screen.stop()


def test_a_timeout_folds_facing_a_bet_and_is_logged(
    qapp: QApplication, fake_time: FakeTime
) -> None:
    screen, game = start(fake_time, dealer_index=0)
    hand = game.hand
    assert hand is not None

    fake_time.now = 30  # 10 s to act + 20 s of time bank.
    tick(screen)

    hero = game.session.players[0]
    assert hero.folded
    assert hand.timed_out_actions == [hand.actions[2].sequence]
    assert "Hero ran out of time — folds" in screen.history_view.toPlainText()
    assert screen.clock_bar.isHidden()
    assert screen.action_clock is not None
    assert screen.action_clock.time_bank == 0
    screen.stop()


def test_a_timeout_checks_when_checking_is_free(
    qapp: QApplication, fake_time: FakeTime
) -> None:
    # Hero is the Big Blind: the bots limp, Hero may check.
    screen, game = start(fake_time, dealer_index=1)
    play_bots(screen, qapp)
    assert game.is_waiting_for_human
    assert screen.action_panel.call_button.text() == "Check"

    fake_time.now = 30
    tick(screen)

    assert not game.session.players[0].folded
    assert game.hand is not None
    assert game.hand.actions[-1].action == ActionType.CHECK
    assert "Hero ran out of time — checks" in screen.history_view.toPlainText()
    screen.stop()


def test_the_time_bank_carries_over_to_the_next_decision(
    qapp: QApplication, fake_time: FakeTime
) -> None:
    screen, game = start(fake_time, dealer_index=0)

    fake_time.now = 14  # 4 s of time bank used.
    tick(screen)
    screen.action_panel.call_button.click()
    clock = screen.action_clock
    assert clock is not None and clock.time_bank == 16

    play_bots(screen, qapp)  # The flop, back to Hero.
    assert game.is_waiting_for_human
    assert clock.is_turn_running
    assert clock.time_bank == 16, "no reset between decisions"
    screen.stop()


def test_pause_freezes_the_clock_and_resumes_where_it_was(
    qapp: QApplication, fake_time: FakeTime
) -> None:
    screen, game = start(fake_time, dealer_index=0)
    clock = screen.action_clock
    assert clock is not None
    assert not screen.pause_button.isHidden()

    fake_time.now = 7
    screen.toggle_pause()
    assert screen.paused and clock.is_paused
    assert not screen.action_panel.call_button.isEnabled()

    fake_time.now = 500
    tick(screen)
    assert not game.session.players[0].folded
    assert clock.time_to_act_left() == pytest.approx(3)

    screen.toggle_pause()
    assert not clock.is_paused
    assert clock.time_to_act_left() == pytest.approx(3)
    assert screen.action_panel.call_button.isEnabled()
    screen.stop()


def test_without_a_clock_there_is_no_timeout_and_no_pause(
    qapp: QApplication, fake_time: FakeTime
) -> None:
    screen = GameScreen()
    screen.clock_time_source = fake_time
    game = make_game(dealer_index=0)
    screen.start_game(game, human_name=HUMAN)  # Off.

    fake_time.now = 10_000
    tick(screen)

    assert screen.action_clock is None
    assert screen.clock_bar.isHidden()
    assert screen.pause_button.isHidden()
    assert game.is_waiting_for_human
    screen.stop()


def test_the_time_bank_is_topped_up_after_hands(
    qapp: QApplication, fake_time: FakeTime
) -> None:
    screen, game = start(fake_time, dealer_index=0)  # Top-up every hand.
    fake_time.now = 30
    tick(screen)  # Hero times out and folds; the bots finish the hand.
    play_bots(screen, qapp)
    assert game.hand is not None and game.hand.finished

    clock = screen.action_clock
    assert clock is not None
    assert clock.time_bank == 5
    screen.stop()


def test_setup_screens_default_and_remember_the_clock(
    qapp: QApplication, tmp_path: Path
) -> None:
    path = tmp_path / "profile.json"
    window = MainWindow(save_sessions=False, profile=ProfileStore(path))
    tournament = window.tournament_setup_screen

    assert window.cash_setup_screen.clock_combo.choice() == "Standard"
    assert window.spin_setup_screen.clock_combo.choice() == "Fast"
    assert tournament.clock_combo.choice() == "Fast", "Turbo by default"

    tournament.structure_combo.setCurrentIndex(
        tournament.structure_combo.findData("Regular")
    )
    assert tournament.clock_combo.choice() == "Standard"

    combo = window.cash_setup_screen.clock_combo
    combo.activated.emit(combo.findData("Hyper"))  # The user picks Hyper.
    window.close()

    reopened = MainWindow(save_sessions=False, profile=ProfileStore(path))
    assert reopened.cash_setup_screen.clock_combo.choice() == "Hyper"
    assert reopened.cash_setup_screen.clock_combo.preset() == clock_preset("Hyper")
    reopened.close()


def test_a_cash_game_starts_with_the_chosen_clock(qapp: QApplication) -> None:
    window = MainWindow(save_sessions=False)
    window.start_game(window.cash_setup_screen.current_settings())

    clock = window.game_screen.action_clock
    assert clock is not None and clock.preset.name == "Standard"
    window.close()
