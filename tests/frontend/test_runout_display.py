"""The table once an all-in is called: cards face up, equity, slower streets."""

from PySide6.QtWidgets import QApplication

from backend.application.controllers import (
    DecisionContext,
    HumanController,
    PlayerController,
)
from backend.application.game import PokerGame
from backend.poker_engine.actions import Action
from backend.poker_engine.constants import ActionType
from backend.poker_engine.session import GameConfig, create_session
from backend.simulation.config import SeatSpec, SimulationConfig
from frontend.runout import RUNOUT_DELAY_FACTOR
from frontend.ui.arena_watch_screen import ArenaWatchScreen
from frontend.ui.game_screen import GameScreen

HUMAN = "Hero"


class Shover(PlayerController):
    def choose_action(self, context: DecisionContext) -> Action:
        return Action(type=ActionType.ALL_IN)


def heads_up_against_a_shover() -> PokerGame:
    """Hero has the button (small blind) and acts first pre-flop."""
    session = create_session(
        [HUMAN, "Bot"],
        GameConfig(starting_stack=200, rebuy_stack=200, small_blind=5, big_blind=10),
    )
    session.table.dealer_index = 0

    return PokerGame(session, {HUMAN: HumanController(), "Bot": Shover()})


def test_calling_an_all_in_turns_the_cards_up_before_the_flop(
    qapp: QApplication,
) -> None:
    screen = GameScreen()
    screen.step_delay_ms = 800
    game = heads_up_against_a_shover()
    screen.start_game(game, human_name=HUMAN)
    hand = game.hand
    assert hand is not None and hand.first_to_act is not None
    assert hand.first_to_act.name == HUMAN

    screen.action_panel.call_button.click()  # Hero completes the small blind.
    screen._play_step()  # noqa: SLF001 - the Bot shoves.
    bot_cards = screen.table_widget.seat_widgets[1].card_widgets
    assert not bot_cards[0].is_face_up, "Hero still has to decide"

    screen.action_panel.call_button.click()  # Hero calls the all-in.

    assert hand.revealed_after_action is not None
    assert hand.community_cards == []
    assert all(card.is_face_up for card in bot_cards)
    history = screen.history_view.toPlainText()
    assert "*** Cards revealed ***" in history
    assert history.index("Hero: calls") < history.index("*** Cards revealed ***")

    # Each player's estimated equity, before the flop.
    statuses = [seat.status_label.text() for seat in screen.table_widget.seat_widgets]
    assert all("≈ " in status and status.endswith("%") for status in statuses)

    # The board comes one street at a time, slower than an action.
    expected_delay = round(800 * RUNOUT_DELAY_FACTOR)
    assert screen._step_timer.interval() == expected_delay  # noqa: SLF001

    screen._play_step()  # noqa: SLF001 - the flop.
    assert len(hand.community_cards) == 3
    status = screen.table_widget.seat_widgets[0].status_label.text()
    assert "≈" not in status and status.endswith("%"), "exact from the flop"

    screen._play_step()  # noqa: SLF001 - the turn.
    screen._play_step()  # noqa: SLF001 - the river.
    screen._play_step()  # noqa: SLF001 - the showdown.

    assert hand.finished
    assert "%" not in screen.table_widget.seat_widgets[0].status_label.text()
    history = screen.history_view.toPlainText()
    assert history.count("*** Cards revealed ***") == 1
    screen.stop()


def test_watch_mode_reveals_the_cards_of_an_all_in_called(qapp: QApplication) -> None:
    screen = ArenaWatchScreen()
    screen.spectator_check.setChecked(False)
    config = SimulationConfig(seats=(SeatSpec("maniac"), SeatSpec("maniac")), seed=3)
    screen.start(config)
    screen.stop()  # Drive the steps by hand.

    for _ in range(2000):
        hand = screen.hand
        assert hand is not None

        if hand.revealed_after_action is not None and not hand.finished:
            break

        screen.step()
    else:
        raise AssertionError("No all-in was called.")

    seats = screen.table_widget.seat_widgets
    active = {player.name for player in hand.table.players if player.is_active}

    for seat in seats:
        if seat.name_label.text() in active:
            assert seat.card_widgets[0].is_face_up
            assert seat.status_label.text().endswith("%")

    assert "*** Cards revealed ***" in screen.history_view.toPlainText()
