"""Closing a table screen while timers are pending: nothing fires or crashes.

Regression test for a crash on CI ("shared QObject was deleted directly",
then a segmentation fault): Qt objects must be stopped and destroyed while
the application exists, and no callback may reach a destroyed screen.
"""

import random
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QTimer, QtMsgType, qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from backend.application.action_clock import ClockPreset
from backend.application.controllers import (
    DecisionContext,
    HumanController,
    PlayerController,
)
from backend.application.game import PokerGame
from backend.application.setup import SpinSettings, create_spin_and_go
from backend.poker_engine.actions import Action
from backend.poker_engine.constants import ActionType
from backend.poker_engine.session import GameConfig, create_session
from frontend.ui.game_screen import GameScreen
from frontend.ui.tournament_screen import REVEAL_HOLD_MS, TournamentScreen

HUMAN = "Hero"
SHORT_CLOCK = ClockPreset(
    "Short", 0.05, 0.05, top_up=0, top_up_every_hands=1, max_time_bank=1
)
"""Runs out within the wait below, if anything still ran it."""
WAIT_MS = 400
IGNORED = ("propagateSizeHints", "QFontDatabase")
"""Harmless messages of the offscreen platform."""


class Shover(PlayerController):
    def choose_action(self, context: DecisionContext) -> Action:
        return Action(type=ActionType.ALL_IN)


@pytest.fixture
def qt_warnings(qapp: QApplication) -> Iterator[list[str]]:
    """Every Qt warning emitted during the test."""
    messages: list[str] = []

    def handler(kind: QtMsgType, context: object, message: str) -> None:
        if kind != QtMsgType.QtDebugMsg and not any(i in message for i in IGNORED):
            messages.append(message)

    previous = qInstallMessageHandler(handler)
    yield messages
    qInstallMessageHandler(previous)


def heads_up(
    step_delay_ms: int, clock: ClockPreset | None
) -> tuple[GameScreen, PokerGame]:
    """Hero (button, acts first) against a bot that always shoves."""
    session = create_session(
        [HUMAN, "Bot"],
        GameConfig(starting_stack=200, rebuy_stack=200, small_blind=5, big_blind=10),
    )
    session.table.dealer_index = 0
    game = PokerGame(session, {HUMAN: HumanController(), "Bot": Shover()})
    screen = GameScreen()
    screen.step_delay_ms = step_delay_ms
    screen.show()
    screen.start_game(game, HUMAN, clock=clock)

    return screen, game


def close_now(screen: GameScreen) -> None:
    """What leaving a screen does: stop it, close it, let Qt delete it."""
    screen.stop()
    assert active_timers(screen) == [], "stop() stops every timer"
    screen.close()
    screen.deleteLater()


def active_timers(screen: GameScreen) -> list[str]:
    return [
        timer.objectName() or repr(timer)
        for timer in screen.findChildren(QTimer)
        if timer.isActive()
    ]


def test_closing_with_the_clock_running(
    qapp: QApplication, qt_warnings: list[str]
) -> None:
    screen, game = heads_up(step_delay_ms=0, clock=SHORT_CLOCK)
    hand = game.hand
    assert hand is not None and game.is_waiting_for_human
    assert screen.action_clock is not None and screen.action_clock.is_turn_running
    actions = len(hand.actions)

    close_now(screen)
    QTest.qWait(WAIT_MS)

    assert len(hand.actions) == actions, "the clock never timed Hero out"
    assert not game.session.players[0].folded
    assert qt_warnings == []


def test_closing_during_a_run_out_with_equity_shown(
    qapp: QApplication, qt_warnings: list[str]
) -> None:
    screen, game = heads_up(step_delay_ms=50, clock=SHORT_CLOCK)
    hand = game.hand
    assert hand is not None

    screen.action_panel.call_button.click()  # Hero completes the blind…
    QTest.qWait(10)
    screen._play_step()  # noqa: SLF001 - …the Bot shoves…
    screen.action_panel.call_button.click()  # …and Hero calls: run-out.

    assert hand.revealed_after_action is not None and not hand.finished
    statuses = [seat.status_label.text() for seat in screen.table_widget.seat_widgets]
    assert all(status.endswith("%") for status in statuses), "equity is shown"
    assert screen._step_timer.isActive()  # noqa: SLF001 - the flop is pending
    board = list(hand.community_cards)

    close_now(screen)
    QTest.qWait(WAIT_MS)

    assert hand.community_cards == board, "no street was dealt after closing"
    assert qt_warnings == []


def test_closing_during_the_spin_reveal(
    qapp: QApplication, qt_warnings: list[str]
) -> None:
    screen = TournamentScreen()
    screen.show()
    tournament = create_spin_and_go(SpinSettings(), HumanController(), random.Random(3))
    screen.start_tournament(tournament, HUMAN, clock=SHORT_CLOCK)

    while screen._reveal_values:  # noqa: SLF001 - the hold before dealing starts
        screen._reveal_tick()  # noqa: SLF001

    close_now(screen)
    QTest.qWait(REVEAL_HOLD_MS + WAIT_MS)

    assert tournament.hand is None, "the first hand was never dealt"
    assert qt_warnings == []
