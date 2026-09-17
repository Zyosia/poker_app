# backend/game/controllers/base.py

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..constants import Card, Position, Street
from ..models.action_types import Action, LegalAction


@dataclass(frozen=True)
class PlayerView:
    """Public view of a player available to a controller."""

    name: str
    stack: int
    current_bet: int
    total_contribution: int
    position: Position | None
    folded: bool
    all_in: bool
    is_current_player: bool


@dataclass(frozen=True)
class DecisionContext:
    """Information available to a player when making a decision."""

    player: PlayerView
    hole_cards: tuple[Card, ...]
    community_cards: tuple[Card, ...]
    pot: int
    current_bet: int
    legal_actions: tuple[LegalAction, ...]
    players: tuple[PlayerView, ...]
    street: Street


class PlayerController(ABC):
    """Interface used by the poker engine to request player decisions."""

    @abstractmethod
    async def get_action(
        self,
        context: DecisionContext,
    ) -> Action:
        """Return the action selected by the player."""
        raise NotImplementedError
