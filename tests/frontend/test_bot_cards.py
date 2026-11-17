"""Seeing the bots' cards: at showdown only, at the end of the hand, or always.

Only what the user sees changes: the bots still decide with their own two
cards and the public information, nothing more.
"""

from collections.abc import Callable

import pytest
from PySide6.QtWidgets import QApplication

from backend.application.controllers import (
    DecisionContext,
    HumanController,
    PlayerController,
)
from backend.application.game import PokerGame
from backend.application.profile import BotCards
from backend.poker_engine.actions import Action
from backend.poker_engine.session import GameConfig, create_session
from frontend.ui.game_screen import GameScreen, build_table_state
from tests.frontend.test_game_screen import HUMAN, FoldingBot, PassiveBot, make_game

ProcessUntil = Callable[[Callable[[], bool]], None]


def faces(screen: GameScreen) -> list[bool]:
    """Whether each seat shows its cards, Hero first."""
    return [seat.cards_face_up for seat in screen.table_widget.state.seats]


@pytest.fixture
def screen(qapp: QApplication) -> GameScreen:
    game_screen = GameScreen()
    game_screen.step_delay_ms = 0
    game_screen.set_auto_next_hand(False)

    return game_screen


# --- What the table shows -------------------------------------------------------


@pytest.mark.parametrize(
    ("bot_cards", "face_up"),
    [
        (BotCards.SHOWDOWN, False),
        (BotCards.HAND_END, False),
        (BotCards.ALWAYS, True),
    ],
)
def test_during_a_hand_only_always_shows_the_bots_cards(
    bot_cards: BotCards, face_up: bool
) -> None:
    hand = make_game(dealer_index=0).start_hand()

    state = build_table_state(hand, human_name=HUMAN, bot_cards=bot_cards)

    assert [seat.cards_face_up for seat in state.seats] == [True, face_up, face_up]


@pytest.mark.parametrize(
    ("bot_cards", "face_up"),
    [
        (BotCards.SHOWDOWN, False),
        (BotCards.HAND_END, True),
        (BotCards.ALWAYS, True),
    ],
)
def test_once_the_hand_is_over_folded_bots_are_shown_too(
    bot_cards: BotCards,
    face_up: bool,
    screen: GameScreen,
    process_until: ProcessUntil,
) -> None:
    game = make_game(dealer_index=0)
    screen.set_bot_cards(bot_cards)
    screen.start_game(game, human_name=HUMAN)
    process_until(lambda: game.is_waiting_for_human)

    screen.action_panel.raise_button.click()  # Hero bets...
    game.controllers["Bot1"] = FoldingBot()  # ...and both bots fold.
    game.controllers["Bot2"] = FoldingBot()
    process_until(lambda: game.hand is not None and game.hand.finished)

    assert faces(screen) == [True, face_up, face_up]
    assert all(seat.dimmed for seat in screen.table_widget.state.seats[1:])


def test_changing_the_setting_turns_the_cards_at_once(
    screen: GameScreen, process_until: ProcessUntil
) -> None:
    game = make_game(dealer_index=0)
    screen.start_game(game, human_name=HUMAN)
    process_until(lambda: game.is_waiting_for_human)
    assert faces(screen) == [True, False, False]

    screen.set_bot_cards(BotCards.ALWAYS)
    assert faces(screen) == [True, True, True]

    screen.set_bot_cards(BotCards.SHOWDOWN)
    assert faces(screen) == [True, False, False]


def test_the_history_lists_the_cards_nobody_showed(
    screen: GameScreen, process_until: ProcessUntil
) -> None:
    game = make_game(dealer_index=0)
    screen.set_bot_cards(BotCards.HAND_END)
    screen.start_game(game, human_name=HUMAN)
    process_until(lambda: game.is_waiting_for_human)

    screen.action_panel.raise_button.click()
    game.controllers["Bot1"] = FoldingBot()
    game.controllers["Bot2"] = FoldingBot()
    process_until(lambda: game.hand is not None and game.hand.finished)

    history = screen.history_view.text()
    assert "Bot1 had " in history and "(folded)" in history
    assert f"{HUMAN} had" not in history


def test_at_showdown_only_the_history_lists_no_hidden_cards(
    screen: GameScreen, process_until: ProcessUntil
) -> None:
    game = make_game(dealer_index=0)
    screen.start_game(game, human_name=HUMAN)
    process_until(lambda: game.is_waiting_for_human)

    screen.action_panel.raise_button.click()
    game.controllers["Bot1"] = FoldingBot()
    game.controllers["Bot2"] = FoldingBot()
    process_until(lambda: game.hand is not None and game.hand.finished)

    assert " had " not in screen.history_view.text()


# --- The bots see nothing more ---------------------------------------------------


class SpyBot(PlayerController):
    """Checks or calls, and keeps every decision context it was given."""

    def __init__(self) -> None:
        self.contexts: list[DecisionContext] = []

    def choose_action(self, context: DecisionContext) -> Action:
        self.contexts.append(context)
        return PassiveBot().choose_action(context)


def test_the_bots_only_ever_see_their_own_cards(
    screen: GameScreen, process_until: ProcessUntil
) -> None:
    session = create_session(
        [HUMAN, "Spy1", "Spy2"],
        GameConfig(starting_stack=500, rebuy_stack=500, small_blind=5, big_blind=10),
    )
    session.table.dealer_index = 0
    spies = {"Spy1": SpyBot(), "Spy2": SpyBot()}
    controllers: dict[str, PlayerController] = {**spies, HUMAN: HumanController()}
    game = PokerGame(session=session, controllers=controllers)
    screen.set_bot_cards(BotCards.ALWAYS)
    screen.start_game(game, human_name=HUMAN)

    for _ in range(3):  # Three hands, Hero checking or calling to the river.
        hand = game.hand
        assert hand is not None

        while not hand.finished:
            if game.is_waiting_for_human:
                assert faces(screen) == [True, True, True]  # The user sees all.
                screen.action_panel.call_button.click()

            process_until(lambda hand=hand: game.is_waiting_for_human or hand.finished)

        hole_cards = {player.name: set(player.hand) for player in hand.table.players}

        for name, spy in spies.items():
            others = set().union(
                *(cards for n, cards in hole_cards.items() if n != name)
            )

            assert spy.contexts  # Every bot decided at least once.

            for context in spy.contexts:
                seen = set(context.hole_cards) | set(context.community_cards)
                assert set(context.hole_cards) == hole_cards[name]
                assert not seen & others

            spy.contexts.clear()

        screen.next_hand_button.click()
