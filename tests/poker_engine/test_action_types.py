from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.constants import ActionType


def test_action_without_amount():
    action = Action(
        type=ActionType.FOLD,
    )

    assert action.type == "fold"
    assert action.amount is None


def test_action_with_amount():
    action = Action(
        type=ActionType.RAISE,
        amount=250,
    )

    assert action.type == "raise"
    assert action.amount == 250


def test_legal_action_fixed_amount():
    action = LegalAction(
        type=ActionType.CALL,
        amount=100,
    )

    assert action.type == "call"
    assert action.amount == 100
    assert action.min_amount is None
    assert action.max_amount is None


def test_legal_action_with_amount_range():
    action = LegalAction(
        type=ActionType.RAISE,
        min_amount=200,
        max_amount=1000,
    )

    assert action.type == "raise"
    assert action.amount is None
    assert action.min_amount == 200
    assert action.max_amount == 1000
