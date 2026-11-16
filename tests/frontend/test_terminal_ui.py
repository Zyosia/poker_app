from unittest.mock import patch

from backend.application.controllers import DecisionContext, PlayerView
from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.constants import ActionType, Street
from backend.poker_engine.session import GameConfig, GameSession
from frontend.terminal_ui import (
    TerminalController,
    describe_legal_action,
    handle_rebuys,
)
from tests.helpers import make_player

LEGAL_ACTIONS = (
    LegalAction(type=ActionType.FOLD),
    LegalAction(type=ActionType.CALL, amount=10),
    LegalAction(type=ActionType.RAISE, min_amount=20, max_amount=100),
    LegalAction(type=ActionType.ALL_IN, amount=100),
)


def make_context() -> DecisionContext:
    player = PlayerView("Hero", 100, 0, 0, None, False, False, True)

    return DecisionContext(
        player=player,
        hole_cards=("AS", "KH"),
        community_cards=(),
        pot=15,
        current_bet=10,
        big_blind=10,
        legal_actions=LEGAL_ACTIONS,
        players=(player,),
        street=Street.PREFLOP,
    )


def test_describe_legal_action() -> None:
    assert [describe_legal_action(action) for action in LEGAL_ACTIONS] == [
        "FOLD",
        "CALL (10)",
        "RAISE to 20-100",
        "ALL-IN (100)",
    ]


def test_terminal_controller_returns_the_chosen_action() -> None:
    with patch("builtins.input", side_effect=["2"]), patch("builtins.print"):
        action = TerminalController().choose_action(make_context())

    assert action == Action(type=ActionType.CALL)


def test_terminal_controller_asks_again_after_invalid_input() -> None:
    answers = ["9", "raise", "3", "5", "abc", "40"]

    with patch("builtins.input", side_effect=answers), patch("builtins.print"):
        action = TerminalController().choose_action(make_context())

    assert action == Action(type=ActionType.RAISE, amount=40)


def test_handle_rebuys_rebuys_busted_player() -> None:
    alice = make_player(
        "Alice",
        stack=0,
    )
    bob = make_player(
        "Bob",
        stack=100,
    )

    config = GameConfig(
        starting_stack=100,
        rebuy_stack=500,
        small_blind=5,
        big_blind=10,
    )

    session = GameSession(
        players=[alice, bob],
        config=config,
    )

    with patch(
        "builtins.input",
        return_value="y",
    ):
        handle_rebuys(
            session=session,
        )

    assert alice.stack == 500
    assert alice.is_busted is False
    assert alice.eliminated is False

    assert bob.stack == 100
    assert bob.eliminated is False


def test_handle_rebuys_eliminates_player_who_declines_rebuy() -> None:
    alice = make_player(
        "Alice",
        stack=0,
    )
    bob = make_player(
        "Bob",
        stack=100,
    )

    config = GameConfig(
        starting_stack=100,
        rebuy_stack=500,
        small_blind=5,
        big_blind=10,
    )

    session = GameSession(
        players=[alice, bob],
        config=config,
    )

    with patch(
        "builtins.input",
        return_value="n",
    ):
        handle_rebuys(
            session=session,
        )

    assert alice.stack == 0
    assert alice.is_busted is True
    assert alice.eliminated is True

    assert bob.stack == 100
    assert bob.eliminated is False
