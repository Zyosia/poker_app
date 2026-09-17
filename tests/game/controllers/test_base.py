# tests/game/controllers/test_base.py

import asyncio

from backend.game.controllers.base import (
    DecisionContext,
    PlayerController,
    PlayerView,
)
from backend.game.models.action_types import Action


class TestController(PlayerController):
    async def get_action(
        self,
        context: DecisionContext,
    ) -> Action:
        return Action(
            type="check",
        )


def test_controller_can_receive_decision_context():
    player = PlayerView(
        name="Alice",
        stack=1000,
        current_bet=10,
        total_contribution=10,
        position="BTN",
        folded=False,
        all_in=False,
        is_current_player=True,
    )

    context = DecisionContext(
        player=player,
        hole_cards=("AS", "KH"),
        community_cards=(),
        pot=15,
        current_bet=10,
        legal_actions=(),
        players=(player,),
        street="PREFLOP",
    )

    controller = TestController()

    result = asyncio.run(
        controller.get_action(context),
    )

    assert result == Action(
        type="check",
    )
