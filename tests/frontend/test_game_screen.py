from collections.abc import Callable

import pytest
from PySide6.QtWidgets import QApplication

from backend.application.controllers import (
    DecisionContext,
    HumanController,
    PlayerController,
)
from backend.application.game import PokerGame
from backend.application.setup import GameSettings
from backend.poker_engine.actions import Action
from backend.poker_engine.constants import ActionType
from backend.poker_engine.session import GameConfig, create_session
from frontend.components.seat_widget import SeatHighlight
from frontend.ui.cash_setup_screen import CashSetupScreen
from frontend.ui.game_screen import GameScreen, build_table_state
from frontend.ui.main_window import MainWindow

ProcessUntil = Callable[[Callable[[], bool]], None]

HUMAN = "Hero"


class PassiveBot(PlayerController):
    """Checks when possible, otherwise calls."""

    def choose_action(self, context: DecisionContext) -> Action:
        legal_types = {action.type for action in context.legal_actions}

        if ActionType.CHECK in legal_types:
            return Action(type=ActionType.CHECK)

        return Action(type=ActionType.CALL)


class FoldingBot(PlayerController):
    def choose_action(self, context: DecisionContext) -> Action:
        return Action(type=ActionType.FOLD)


def make_game(dealer_index: int = 0, opponents: int = 2) -> PokerGame:
    """Create a game where Hero has the first seat against passive bots."""
    bot_names = [f"Bot{index}" for index in range(1, opponents + 1)]
    session = create_session(
        [HUMAN, *bot_names],
        GameConfig(starting_stack=100, rebuy_stack=100, small_blind=5, big_blind=10),
    )
    session.table.dealer_index = dealer_index

    controllers: dict[str, PlayerController] = {
        name: PassiveBot() for name in bot_names
    }
    controllers[HUMAN] = HumanController()

    return PokerGame(session=session, controllers=controllers)


@pytest.fixture
def screen(qapp: QApplication) -> GameScreen:
    game_screen = GameScreen()
    game_screen.step_delay_ms = 0

    return game_screen


# ============================================================
# Table state
# ============================================================


def test_table_state_puts_the_human_at_the_bottom_and_hides_opponent_cards() -> None:
    game = make_game(dealer_index=1)
    hand = game.start_hand()

    state = build_table_state(hand, human_name="Bot1")

    assert [seat.name for seat in state.seats] == ["Bot1", "Bot2", HUMAN]
    assert state.dealer_seat == 0
    assert state.pot == 15
    assert state.community_cards == ()

    # Bot1 is the Button, Bot2 the Small Blind and Hero the Big Blind.
    assert state.bets == (0, 5, 10)

    assert state.seats[0].cards_face_up is True
    assert state.seats[1].cards_face_up is False
    assert state.seats[2].cards_face_up is False
    assert len(state.seats[1].cards) == 2


def test_table_state_highlights_the_player_to_act() -> None:
    game = make_game(dealer_index=0)
    hand = game.start_hand()

    state = build_table_state(hand, human_name=HUMAN)

    # Three-handed, the Button (Hero) acts first pre-flop.
    assert [seat.highlight for seat in state.seats] == [
        SeatHighlight.ACTING,
        SeatHighlight.NONE,
        SeatHighlight.NONE,
    ]
    assert [seat.status for seat in state.seats] == ["BTN", "SB", "BB"]


# ============================================================
# Game flow
# ============================================================


def test_start_game_displays_the_table_and_enables_legal_actions(
    screen: GameScreen,
) -> None:
    game = make_game(dealer_index=0)

    screen.start_game(game, human_name=HUMAN)

    assert game.is_waiting_for_human is True
    assert len(screen.table_widget.seat_widgets) == 3
    assert screen.table_widget.seat_widgets[0].name_label.text() == HUMAN
    assert screen.table_widget.seat_widgets[0].card_widgets[0].is_face_up is True
    assert screen.table_widget.seat_widgets[1].card_widgets[0].is_face_up is False
    assert screen.table_widget.pot_label.text() == "Pot  15"
    assert "HAND #1" in screen.info_label.text()

    panel = screen.action_panel
    assert screen.bottom_stack.currentWidget() is panel
    assert panel.fold_button.isEnabled()
    assert panel.call_button.text() == "Call 10"
    assert panel.raise_button.text() == "Raise to 20"


def test_start_game_requires_a_human_controller(screen: GameScreen) -> None:
    with pytest.raises(ValueError):
        screen.start_game(make_game(), human_name="Bot1")


def test_bots_play_from_the_event_loop_without_blocking(
    screen: GameScreen,
    process_until: ProcessUntil,
) -> None:
    # Hero is the Big Blind: both bots act before him.
    game = make_game(dealer_index=1)

    screen.start_game(game, human_name=HUMAN)

    # Starting the game returns immediately: no bot has played yet and the
    # action panel is disabled while they are thinking.
    assert game.hand is not None
    assert len(game.hand.actions) == 2
    assert game.is_waiting_for_human is False
    assert not screen.action_panel.call_button.isEnabled()

    process_until(lambda: game.is_waiting_for_human)

    assert [event.action for event in game.hand.actions] == [
        "post_sb",
        "post_bb",
        "call",
        "call",
    ]
    assert screen.action_panel.call_button.text() == "Check"
    assert "Bot1: calls 10" in screen.history_view.toPlainText()


def test_human_action_is_applied_and_the_display_updated(
    screen: GameScreen,
    process_until: ProcessUntil,
) -> None:
    game = make_game(dealer_index=0)
    screen.start_game(game, human_name=HUMAN)
    hero = game.session.players[0]

    screen.action_panel.amount_spin.setValue(30)
    screen.action_panel.raise_button.click()

    assert hero.current_bet == 30
    assert hero.stack == 70
    assert screen.table_widget.seat_widgets[0].stack_label.text() == "70"
    assert "Hero: raises to 30" in screen.history_view.toPlainText()
    assert not screen.action_panel.raise_button.isEnabled()

    # Both bots call, then the flop is dealt and Hero acts last.
    process_until(lambda: game.is_waiting_for_human)

    assert game.hand is not None
    assert game.hand.street == "FLOP"
    assert screen.table_widget.pot_label.text() == "Pot  90"
    assert [w.card for w in screen.table_widget.board_widgets[:3]] == (
        game.hand.community_cards
    )
    assert screen.table_widget.board_widgets[3].card is None
    assert "*** FLOP ***" in screen.history_view.toPlainText()


def test_fold_ends_the_hand_and_shows_the_result(screen: GameScreen) -> None:
    game = make_game(dealer_index=0, opponents=1)
    screen.start_game(game, human_name=HUMAN)

    screen.action_panel.fold_button.click()

    assert game.is_hand_in_progress is False
    assert screen.bottom_stack.currentIndex() == 1
    assert screen.result_label.text() == "Bot1 wins 15"
    assert screen.next_hand_button.isVisibleTo(screen)
    assert not screen.rebuy_button.isVisibleTo(screen)
    assert screen.table_widget.seat_widgets[1].status_label.text() == "Wins 15"


def test_next_hand_button_starts_a_new_hand(screen: GameScreen) -> None:
    game = make_game(dealer_index=0, opponents=1)
    screen.start_game(game, human_name=HUMAN)
    screen.action_panel.fold_button.click()

    screen.next_hand_button.click()

    assert game.session.hand_number == 2
    assert game.is_hand_in_progress is True
    assert game.session.table.dealer.name == "Bot1"
    assert "HAND #2" in screen.info_label.text()
    assert screen.table_widget.board_widgets[0].card is None


def test_showdown_reveals_the_cards_of_the_players_involved(
    screen: GameScreen,
    process_until: ProcessUntil,
) -> None:
    game = make_game(dealer_index=0, opponents=1)
    screen.start_game(game, human_name=HUMAN)

    def play() -> bool:
        if game.is_waiting_for_human:
            screen.action_panel.call_button.click()

        return not game.is_hand_in_progress

    process_until(play)

    assert game.hand is not None
    assert len(game.hand.showdown_evaluations) == 2
    assert all(
        card_widget.is_face_up
        for seat_widget in screen.table_widget.seat_widgets
        for card_widget in seat_widget.card_widgets
    )
    assert "Bot1 shows" in screen.history_view.toPlainText()
    assert sum(player.stack for player in game.session.players) == 200


def test_busted_human_can_rebuy(screen: GameScreen) -> None:
    game = make_game(dealer_index=0, opponents=1)
    screen.start_game(game, human_name=HUMAN)
    hero, bot = game.session.players

    # Hero loses his last chips on this hand.
    bot.stack += hero.stack
    hero.stack = 0
    screen.action_panel.fold_button.click()

    assert "out of chips" in screen.result_label.text()
    assert screen.rebuy_button.isVisibleTo(screen)
    assert screen.rebuy_button.text() == "Rebuy 100"
    assert not screen.next_hand_button.isVisibleTo(screen)

    screen.rebuy_button.click()

    assert hero.eliminated is False
    assert game.session.hand_number == 2
    assert game.is_hand_in_progress is True
    assert hero.stack + hero.current_bet == 100


def test_game_is_won_when_every_opponent_is_eliminated(
    screen: GameScreen,
    process_until: ProcessUntil,
) -> None:
    game = make_game(dealer_index=0, opponents=1)
    screen.start_game(game, human_name=HUMAN)
    hero, bot = game.session.players

    # The bot only has its big blind left and loses it.
    hero.stack += bot.stack
    bot.stack = 0
    screen.action_panel.raise_button.click()

    assert game.is_hand_in_progress is True

    game.controllers["Bot1"] = FoldingBot()
    process_until(lambda: not game.is_hand_in_progress)

    assert bot.eliminated is True
    assert "You win the game!" in screen.result_label.text()
    assert not screen.next_hand_button.isVisibleTo(screen)
    assert not screen.rebuy_button.isVisibleTo(screen)
    assert "Bot1 is eliminated" in screen.history_view.toPlainText()


def test_menu_button_stops_the_game(screen: GameScreen) -> None:
    requests: list[bool] = []
    screen.menu_requested.connect(lambda: requests.append(True))
    screen.start_game(make_game(dealer_index=1), human_name=HUMAN)

    screen.menu_button.click()

    assert requests == [True]
    assert screen.game is None


# ============================================================
# Menu and main window
# ============================================================


def test_menu_emits_the_chosen_settings(qapp: QApplication) -> None:
    menu = CashSetupScreen()
    received: list[GameSettings] = []
    menu.start_requested.connect(received.append)

    menu.set_player_name("Nael")
    menu.opponents_spin.setValue(5)
    menu.bot_combos[1].setCurrentIndex(menu.bot_combos[1].findData("random"))
    menu.stack_spin.setValue(2000)
    menu.blinds_combo.setCurrentIndex(1)
    menu.play_button.click()

    assert received == [
        GameSettings(
            player_name="Nael",
            opponents=("tag", "random", "station", "tag", "lag"),
            starting_stack=2000,
            small_blind=10,
            big_blind=20,
        )
    ]


def test_the_cash_setup_seats_up_to_eight_bots_of_any_style(
    qapp: QApplication,
) -> None:
    menu = CashSetupScreen()

    assert menu.opponents_spin.maximum() == 8
    assert sum(not combo.isHidden() for combo in menu.bot_combos) == 3

    menu.opponents_spin.setValue(8)
    assert sum(not combo.isHidden() for combo in menu.bot_combos) == 8
    assert len(menu.current_settings().opponents) == 8

    menu.same_style_check.setChecked(True)
    menu.bot_combos[0].setCurrentIndex(menu.bot_combos[0].findData("maniac"))

    assert sum(not combo.isHidden() for combo in menu.bot_combos) == 1
    assert menu.current_settings().opponents == ("maniac",) * 8


def test_menu_rejects_an_empty_name(qapp: QApplication) -> None:
    menu = CashSetupScreen()
    received: list[GameSettings] = []
    menu.start_requested.connect(received.append)

    menu.set_player_name("   ")
    menu.play_button.click()

    assert received == []
    assert menu.error_label.text() != ""


def test_a_cash_game_opens_in_its_own_window_and_returns_to_its_setup(
    qapp: QApplication,
) -> None:
    window = MainWindow(save_sessions=False)
    assert window.screens.currentWidget() is window.main_menu

    window.main_menu.card("cash").click()
    [table] = window.game_windows
    table.table_screen.step_delay_ms = 0
    assert window.screens.currentWidget() is window.main_menu
    assert table.screens.currentWidget() is table.setup_screen

    setup = table.setup_screen
    assert isinstance(setup, CashSetupScreen)
    setup.opponents_spin.setValue(8)  # A full-ring table.
    setup.play_button.click()

    game = table.table_screen.game

    assert table.screens.currentWidget() is table.table_screen
    assert isinstance(game, PokerGame)
    assert [player.name for player in game.session.players][0] == "Hero"
    assert len(game.session.players) == 9
    assert game.save_path is None
    assert table.windowTitle().startswith(("Cash game 5/10", "Your turn"))

    table.table_screen.menu_button.click()

    assert table.screens.currentWidget() is table.setup_screen
    assert table.table_screen.game is None

    table.setup_screen.back_button.click()  # Back closes the window.

    assert window.game_windows == []
