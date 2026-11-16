import json
from pathlib import Path

import pytest

from backend.application.controllers import (
    DecisionContext,
    HumanController,
    PlayerController,
)
from backend.application.game import PokerGame
from backend.poker_engine.actions import Action
from backend.poker_engine.constants import ActionType
from backend.poker_engine.session import GameConfig, create_session

CONFIG = GameConfig(starting_stack=100, small_blind=5, big_blind=10)


class ScriptedController(PlayerController):
    """Plays a fixed list of actions and records the contexts it receives."""

    def __init__(self, *actions: Action) -> None:
        self.actions = list(actions)
        self.contexts: list[DecisionContext] = []

    def choose_action(self, context: DecisionContext) -> Action:
        self.contexts.append(context)

        return self.actions.pop(0)


def fold() -> Action:
    return Action(type=ActionType.FOLD)


def call() -> Action:
    return Action(type=ActionType.CALL)


def check() -> Action:
    return Action(type=ActionType.CHECK)


def make_game(
    controllers: dict[str, PlayerController],
    save_path: Path | None = None,
) -> PokerGame:
    session = create_session(list(controllers), CONFIG)
    session.table.dealer_index = 0

    return PokerGame(session=session, controllers=controllers, save_path=save_path)


def test_game_requires_a_controller_for_every_player() -> None:
    session = create_session(["Alice", "Bob"], CONFIG)

    with pytest.raises(ValueError, match="Bob"):
        PokerGame(session=session, controllers={"Alice": HumanController()})


def test_step_requires_a_hand_in_progress() -> None:
    game = make_game({"Alice": ScriptedController(), "Bob": ScriptedController()})

    with pytest.raises(RuntimeError):
        game.step()


def test_step_executes_the_decision_of_the_current_player() -> None:
    alice = ScriptedController(call())
    bob = ScriptedController(check())
    game = make_game({"Alice": alice, "Bob": bob})

    hand = game.start_hand()

    # Heads-up: Alice is the Button and acts first pre-flop.
    assert game.current_player is game.session.players[0]

    event = game.step()

    assert event is not None
    assert event.player == "Alice"
    assert event.action == "call"
    assert game.current_player is game.session.players[1]

    game.step()

    # The betting round is over: the next step deals the flop.
    assert game.current_player is None
    assert game.step() is None
    assert hand.street == "FLOP"
    assert len(hand.community_cards) == 3


def test_complete_hand_preserves_chips_and_finishes() -> None:
    alice = ScriptedController(call(), check(), check(), check())
    bob = ScriptedController(check(), check(), check(), check())
    game = make_game({"Alice": alice, "Bob": bob})

    hand = game.start_hand()

    while game.is_hand_in_progress:
        game.step()

    assert hand.finished is True
    assert hand.pot == 0
    assert sum(player.stack for player in game.session.players) == 200
    assert game.current_player is None


def test_context_only_exposes_information_the_player_may_see() -> None:
    alice = ScriptedController(fold())
    game = make_game({"Alice": alice, "Bob": ScriptedController()})

    game.start_hand()
    alice_player, bob_player = game.session.players
    game.step()

    context = alice.contexts[0]

    assert context.hole_cards == tuple(alice_player.hand)
    assert context.player.name == "Alice"
    assert context.player.is_current_player is True
    assert context.pot == 15
    assert context.current_bet == 10
    assert context.big_blind == 10
    assert context.street == "PREFLOP"
    assert [action.type for action in context.legal_actions] == [
        "fold",
        "call",
        "raise",
        "all_in",
    ]

    # Opponents are only described by public information.
    opponent_view = next(view for view in context.players if view.name == "Bob")

    assert not hasattr(opponent_view, "hand")
    assert not hasattr(opponent_view, "hole_cards")
    assert not any(card in repr(context.players) for card in bob_player.hand)


def test_game_waits_for_the_human_until_an_action_is_submitted() -> None:
    human = HumanController()
    game = make_game({"Alice": human, "Bob": ScriptedController(check())})

    game.start_hand()

    assert game.is_waiting_for_human is True

    with pytest.raises(RuntimeError):
        game.step()

    human.submit(call())

    assert game.is_waiting_for_human is False

    game.step()

    # It is now the bot's turn.
    assert game.current_player is game.session.players[1]
    assert game.is_waiting_for_human is False


def test_illegal_human_action_is_rejected_and_can_be_corrected() -> None:
    human = HumanController()
    game = make_game({"Alice": human, "Bob": ScriptedController()})

    game.start_hand()
    human.submit(check())

    with pytest.raises(ValueError):
        game.step()

    assert game.is_waiting_for_human is True

    human.submit(fold())
    game.step()

    assert game.is_hand_in_progress is False


def test_next_hand_moves_the_button_and_eliminates_busted_players() -> None:
    game = make_game(
        {
            "Alice": ScriptedController(fold()),
            "Bob": ScriptedController(fold()),
            "Charlie": ScriptedController(),
        }
    )
    alice, bob, charlie = game.session.players

    # Alice (Button) then Bob (Small Blind) fold: Charlie wins the blinds.
    game.start_hand()
    game.step()

    assert game.is_hand_in_progress is True

    game.step()

    assert game.is_hand_in_progress is False

    with pytest.raises(RuntimeError):
        game.step()

    # Bob loses his whole stack before the next hand.
    charlie.stack += bob.stack
    bob.stack = 0

    assert game.can_start_hand() is True

    hand = game.start_hand()

    assert bob.eliminated is True
    assert bob.hand == []
    assert game.session.table.dealer is charlie
    assert charlie.position == "BTN"
    assert alice.position == "BB"
    assert hand.current_player is charlie


def test_game_cannot_start_a_hand_with_a_single_player_left() -> None:
    game = make_game({"Alice": ScriptedController(), "Bob": ScriptedController()})
    alice, bob = game.session.players
    alice.stack += bob.stack
    bob.stack = 0

    assert game.can_start_hand() is False

    with pytest.raises(RuntimeError):
        game.start_hand()


def test_session_is_saved_when_a_hand_finishes(tmp_path: Path) -> None:
    save_path = tmp_path / "sessions" / "game.dat"
    game = make_game(
        {"Alice": ScriptedController(fold()), "Bob": ScriptedController()},
        save_path=save_path,
    )

    game.start_hand()

    assert not save_path.exists()

    game.step()

    data = json.loads(save_path.read_text(encoding="utf-8"))

    assert data["session"]["hand_count"] == 1
    assert data["hands"][0]["winner_by_fold"] == "Bob"
    assert data["hands"][0]["actions"][-1]["action"] == "fold"
