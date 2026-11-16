import pytest

from backend.application.controllers import (
    DecisionContext,
    HumanController,
    PlayerController,
    PlayerView,
)
from backend.poker_engine.actions import Action
from backend.poker_engine.constants import ActionType, Position, Street


def make_context() -> DecisionContext:
    player = PlayerView(
        name="Alice",
        stack=1000,
        current_bet=10,
        total_contribution=10,
        position=Position.BTN,
        folded=False,
        all_in=False,
        is_current_player=True,
    )

    return DecisionContext(
        player=player,
        hole_cards=("AS", "KH"),
        community_cards=(),
        pot=15,
        current_bet=10,
        big_blind=10,
        legal_actions=(),
        players=(player,),
        street=Street.PREFLOP,
    )


class AlwaysCheckController(PlayerController):
    def choose_action(self, context: DecisionContext) -> Action:
        return Action(type=ActionType.CHECK)


def test_controller_can_receive_decision_context() -> None:
    controller = AlwaysCheckController()

    assert controller.choose_action(make_context()) == Action(type=ActionType.CHECK)


def test_human_controller_returns_the_submitted_action_once() -> None:
    controller = HumanController()

    assert controller.has_pending_action is False

    controller.submit(Action(type=ActionType.RAISE, amount=40))

    assert controller.has_pending_action is True
    assert controller.choose_action(make_context()) == Action(
        type=ActionType.RAISE,
        amount=40,
    )
    assert controller.has_pending_action is False


def test_human_controller_requires_a_submitted_action() -> None:
    controller = HumanController()

    with pytest.raises(RuntimeError):
        controller.choose_action(make_context())
