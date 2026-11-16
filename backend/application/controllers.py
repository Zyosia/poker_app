"""Player controllers: who decides which action a player takes.

A controller only chooses an action. The poker engine stays responsible for
validating and executing it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.constants import Card, Position, Street


@dataclass(frozen=True)
class PlayerView:
    """Public information about a player, visible to everyone at the table."""

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
    """Everything a player may legitimately know when making a decision.

    It never contains the hole cards of the other players.
    """

    player: PlayerView
    hole_cards: tuple[Card, ...]
    community_cards: tuple[Card, ...]
    pot: int
    current_bet: int
    big_blind: int
    legal_actions: tuple[LegalAction, ...]
    players: tuple[PlayerView, ...]
    street: Street


class PlayerController(ABC):
    """Decides the actions of one player."""

    is_human = False
    """Human players may rebuy when busted; bots are eliminated."""

    @abstractmethod
    def choose_action(self, context: DecisionContext) -> Action:
        """Return the action selected by the player."""


class HumanController(PlayerController):
    """Controller of a human player.

    The user interface submits the decision of the user, which is then
    consumed when the game asks for the player's action.
    """

    is_human = True

    def __init__(self) -> None:
        self._pending_action: Action | None = None

    @property
    def has_pending_action(self) -> bool:
        return self._pending_action is not None

    def submit(self, action: Action) -> None:
        """Store the action chosen by the user."""
        self._pending_action = action

    def choose_action(self, context: DecisionContext) -> Action:
        if self._pending_action is None:
            raise RuntimeError("No action has been submitted for the human player.")

        action = self._pending_action
        self._pending_action = None

        return action
