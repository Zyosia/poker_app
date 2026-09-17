from backend.game.models.action_types import Action, LegalAction


def test_action_without_amount():
    action = Action(
        type="fold",
    )

    assert action.type == "fold"
    assert action.amount is None


def test_action_with_amount():
    action = Action(
        type="raise",
        amount=250,
    )

    assert action.type == "raise"
    assert action.amount == 250


def test_legal_action_fixed_amount():
    action = LegalAction(
        type="call",
        amount=100,
    )

    assert action.type == "call"
    assert action.amount == 100
    assert action.min_amount is None
    assert action.max_amount is None


def test_legal_action_with_amount_range():
    action = LegalAction(
        type="raise",
        min_amount=200,
        max_amount=1000,
    )

    assert action.type == "raise"
    assert action.amount is None
    assert action.min_amount == 200
    assert action.max_amount == 1000
