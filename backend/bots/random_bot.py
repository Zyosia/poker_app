"""A bot playing uniformly random legal actions."""

import random

from backend.application.controllers import DecisionContext, PlayerController
from backend.poker_engine.actions import Action
from backend.poker_engine.constants import ActionType


class RandomBot(PlayerController):
    """Selects an action randomly among the legal actions."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def choose_action(self, context: DecisionContext) -> Action:
        legal_action = self._rng.choice(context.legal_actions)

        if legal_action.type != ActionType.RAISE:
            return Action(type=legal_action.type)

        assert legal_action.min_amount is not None
        assert legal_action.max_amount is not None

        return Action(
            type=ActionType.RAISE,
            amount=self._rng.randint(legal_action.min_amount, legal_action.max_amount),
        )
