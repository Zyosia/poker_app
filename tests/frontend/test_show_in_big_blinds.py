"""The "Show in BB" toggle: every amount on the table and the action panel."""

import random
from pathlib import Path

from PySide6.QtWidgets import QApplication

from backend.application.controllers import (
    DecisionContext,
    HumanController,
    PlayerController,
)
from backend.application.game import PokerGame
from backend.application.profile import ProfileStore
from backend.application.setup import SpinSettings, create_spin_and_go
from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.blinds import BlindLevel
from backend.poker_engine.constants import ActionType
from backend.poker_engine.session import GameConfig, create_session
from backend.simulation.config import SeatSpec, SimulationConfig
from frontend.components.action_panel import ActionPanel
from frontend.ui.arena_watch_screen import ArenaWatchScreen
from frontend.ui.game_screen import GameScreen
from frontend.ui.main_window import MainWindow
from frontend.ui.tournament_screen import TournamentScreen
from tests.frontend.windows import open_table

HUMAN = "Hero"


class Caller(PlayerController):
    def choose_action(self, context: DecisionContext) -> Action:
        legal = {action.type for action in context.legal_actions}

        can_check = ActionType.CHECK in legal

        return Action(type=ActionType.CHECK if can_check else ActionType.CALL)


def make_game(dealer_index: int) -> PokerGame:
    """Hero, Bot1 and Bot2 with 100 chips each, blinds 5/10."""
    session = create_session(
        [HUMAN, "Bot1", "Bot2"],
        GameConfig(starting_stack=100, rebuy_stack=100, small_blind=5, big_blind=10),
    )
    session.table.dealer_index = dealer_index
    controllers: dict[str, PlayerController] = {"Bot1": Caller(), "Bot2": Caller()}
    controllers[HUMAN] = HumanController()

    return PokerGame(session=session, controllers=controllers)


FACING_A_BET = (
    LegalAction(type=ActionType.FOLD),
    LegalAction(type=ActionType.CALL, amount=40),
    LegalAction(type=ActionType.RAISE, min_amount=90, max_amount=1017),
    LegalAction(type=ActionType.ALL_IN, amount=1017),
)


def make_panel(big_blind: int | None) -> ActionPanel:
    panel = ActionPanel()
    panel.set_legal_actions(FACING_A_BET, pot=70, current_bet=50, player_bet=10)
    panel.set_big_blind(big_blind)

    return panel


# --- Action panel -------------------------------------------------------------


def test_the_action_panel_labels_follow_the_unit(qapp: QApplication) -> None:
    panel = make_panel(big_blind=20)

    assert panel.call_button.text() == "Call 2 BB"
    assert panel.raise_button.text() == "Raise to 4.5 BB"
    assert panel.amount_spin.suffix() == " BB"
    assert panel.amount_spin.value() == 4.5

    panel.set_big_blind(None)

    assert panel.call_button.text() == "Call 40"
    assert panel.raise_button.text() == "Raise to 90"
    assert panel.amount_spin.value() == 90


def test_presets_and_the_slider_show_big_blinds(qapp: QApplication) -> None:
    panel = make_panel(big_blind=20)

    # Pot after the call: 70 + 50 - 10 = 110, so a pot raise is to 160.
    panel.preset_buttons["Pot"].click()
    assert panel.amount == 160
    assert panel.amount_spin.value() == 8
    assert panel.raise_button.text() == "Raise to 8 BB"

    panel.preset_buttons["Max"].click()
    assert panel.amount == 1017
    assert panel.raise_button.text() == "All-in 50.9 BB"

    panel.amount_slider.setValue(333)
    assert panel.amount == 333  # The slider keeps exact chips.
    assert panel.amount_spin.value() == 16.6  # 16.65 shown to one decimal.


def test_an_amount_typed_in_big_blinds_is_a_legal_chip_amount(
    qapp: QApplication,
) -> None:
    panel = make_panel(big_blind=20)
    sent = []
    panel.action_chosen.connect(sent.append)

    panel.amount_spin.setValue(12.3)
    assert panel.amount == 246
    panel.raise_button.click()
    assert sent[-1].amount == 246

    panel.amount_spin.setValue(panel.amount_spin.maximum())  # 50.9 BB = 1018.
    assert panel.amount == 1017  # The exact all-in, not above it.

    panel.amount_spin.setValue(panel.amount_spin.minimum())  # 4.5 BB.
    assert panel.amount == 90


def test_an_uneven_minimum_is_never_rounded_below_the_legal_raise(
    qapp: QApplication,
) -> None:
    panel = ActionPanel()
    panel.set_legal_actions(
        (LegalAction(type=ActionType.RAISE, min_amount=45, max_amount=517),),
        pot=30,
        current_bet=20,
        player_bet=0,
    )
    panel.set_big_blind(20)

    panel.amount_spin.setValue(2.2)  # 44 chips, below the minimum of 45.

    assert panel.amount == 45


# --- Table screens ------------------------------------------------------------


def test_the_cash_table_shows_every_amount_in_big_blinds(qapp: QApplication) -> None:
    screen = GameScreen()
    screen.step_delay_ms = 0
    game = make_game(dealer_index=0)  # Blinds 5/10, stacks 100.
    screen.start_game(game, human_name=HUMAN)
    seats = screen.table_widget.seat_widgets

    screen.big_blinds_check.setChecked(True)

    assert [seat.stack_label.text() for seat in seats] == ["10 BB", "9.5 BB", "9 BB"]
    assert screen.table_widget.bet_texts() == ["0.5 BB", "1 BB"]
    assert screen.table_widget.pot_label.text() == "Pot  1.5 BB"
    assert screen.action_panel.call_button.text() == "Call 1 BB"
    assert screen.action_panel.raise_button.text() == "Raise to 2 BB"

    screen.big_blinds_check.setChecked(False)

    assert seats[0].stack_label.text() == "100"
    assert screen.table_widget.pot_label.text() == "Pot  15"
    assert screen.action_panel.call_button.text() == "Call 10"
    screen.stop()


def test_the_history_stays_in_chips(qapp: QApplication) -> None:
    screen = GameScreen()
    screen.set_show_in_big_blinds(True)
    screen.start_game(make_game(dealer_index=0), human_name=HUMAN)

    assert "Bot2: posts big blind 10" in screen.history_view.toPlainText()
    screen.stop()


def test_a_tournament_uses_the_big_blind_of_the_current_level(
    qapp: QApplication,
) -> None:
    screen = TournamentScreen()
    tournament = create_spin_and_go(SpinSettings(), HumanController(), random.Random(4))
    screen.set_show_in_big_blinds(True)
    screen.start_tournament(tournament, "Hero")
    screen.finish_reveal()
    hand = tournament.hand
    assert hand is not None and hand.blind_level is not None
    big_blind = hand.blind_level.big_blind
    hero = next(p for p in hand.table.players if p.name == "Hero")

    seat = screen.table_widget.seat_widgets[0]
    expected = hero.stack / big_blind
    assert seat.stack_label.text() == f"{expected:g} BB"
    screen.stop()


def test_a_new_level_applies_from_the_next_hand(qapp: QApplication) -> None:
    screen = GameScreen()
    screen.step_delay_ms = 0
    game = make_game(dealer_index=0)
    screen.set_show_in_big_blinds(True)
    screen.start_game(game, human_name=HUMAN)
    assert screen.action_panel.big_blind == 10

    assert game.hand is not None
    game.hand.finished = True  # End the hand without playing it.
    game.session.set_blind_level(BlindLevel(10, 20))
    screen._start_next_hand()  # noqa: SLF001

    assert screen.action_panel.big_blind == 20
    assert screen.table_widget.pot_label.text() == "Pot  1.5 BB"
    screen.stop()


def test_watch_mode_shows_big_blinds(qapp: QApplication) -> None:
    screen = ArenaWatchScreen()
    config = SimulationConfig(
        seats=(SeatSpec("tag"), SeatSpec("lag")),
        hands=1,
        seed=1,
        small_blind=10,
        big_blind=20,
        starting_stack=1000,
    )
    screen.start(config)
    screen.big_blinds_check.setChecked(True)

    texts = [seat.stack_label.text() for seat in screen.table_widget.seat_widgets]

    assert all(text.endswith(" BB") for text in texts)
    assert screen.table_widget.pot_label.text() == "Pot  1.5 BB"
    screen.stop()


# --- The setting is shared and remembered -------------------------------------


def test_the_toggle_is_shared_by_every_table_and_remembered(
    qapp: QApplication, tmp_path: Path
) -> None:
    path = tmp_path / "profile.json"
    window = MainWindow(save_sessions=False, profile=ProfileStore(path))
    cash = open_table(window, "cash")
    tournament = open_table(window, "tournament")

    cash.table_screen.big_blinds_check.setChecked(True)

    assert tournament.table_screen.show_in_big_blinds
    assert window.arena_watch_screen.show_in_big_blinds
    window.close()

    reopened = MainWindow(save_sessions=False, profile=ProfileStore(path))
    assert open_table(reopened, "cash").table_screen.show_in_big_blinds
    assert reopened.arena_watch_screen.big_blinds_check.isChecked()

    reopened.arena_watch_screen.big_blinds_check.setChecked(False)
    assert not ProfileStore(path).settings.show_in_big_blinds
    reopened.close()
