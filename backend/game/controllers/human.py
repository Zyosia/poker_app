# backend/game/controllers/human.py

from __future__ import annotations

from ..models.action_types import Action
from .base import DecisionContext, PlayerController


class HumanController(PlayerController):
    """Controller for a human player."""

    async def get_action(
        self,
        context: DecisionContext,
    ) -> Action:
        raise NotImplementedError
