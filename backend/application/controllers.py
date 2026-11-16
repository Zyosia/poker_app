"""Player controllers: who decides which action a player takes.

A controller only chooses an action. The poker engine stays responsible for
validating and executing it.
"""

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import NamedTuple

from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.betting import get_current_legal_actions, get_legal_actions
from backend.poker_engine.constants import Card, Position, Street
from backend.poker_engine.models import ActionEvent, Hand, Player


class GameFormat(StrEnum):
    """What the chips are worth: bots play short stacks differently in a
    tournament, where busting ends the game."""

    CASH = "cash"
    TOURNAMENT = "tournament"


class PlayerView(NamedTuple):
    """Public information about a player, visible to everyone at the table.

    A named tuple: immutable, and several times cheaper to build than a
    frozen dataclass, which matters since every decision builds one per seat.
    """

    name: str
    stack: int
    current_bet: int
    total_contribution: int
    position: Position | None
    folded: bool
    all_in: bool
    is_current_player: bool


class DecisionContext(NamedTuple):
    """Everything a player may legitimately know when making a decision.

    It never contains the hole cards of the other players. Like
    ``PlayerView`` it is an immutable named tuple, built once per decision.
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
    actions: tuple[ActionEvent, ...] = ()
    """Public actions of the current hand so far, blinds and antes included."""
    ante: int = 0
    """Ante of the hand (per player, or for the table with a big-blind ante)."""
    game_format: GameFormat = GameFormat.CASH


def build_decision_context(
    hand: Hand,
    player: Player,
    big_blind: int,
    game_format: GameFormat = GameFormat.CASH,
) -> DecisionContext:
    """Build the information ``player`` is allowed to see to decide.

    Only the player's own hole cards are included, never the opponents'.
    """
    current_player = hand.current_player
    player_view: PlayerView | None = None
    views: list[PlayerView] = []

    for seat in hand.table.players:
        # Positional arguments, in field order: the fastest way to build it.
        view = PlayerView(
            seat.name,
            seat.stack,
            seat.current_bet,
            seat.total_contribution,
            seat.position,
            seat.folded,
            seat.all_in,
            seat is current_player,
        )
        views.append(view)

        if seat is player:
            player_view = view

    if player_view is None:
        raise ValueError(f"{player.name} is not seated at this table.")

    return DecisionContext(
        player=player_view,
        hole_cards=tuple(player.hand),
        community_cards=tuple(hand.community_cards),
        pot=hand.pot,
        current_bet=hand.current_bet,
        big_blind=big_blind,
        legal_actions=(
            get_current_legal_actions(hand)
            if player is current_player
            else get_legal_actions(player=player, hand=hand)
        ),
        players=tuple(views),
        street=hand.street,
        actions=tuple(hand.actions),
        ante=hand.blind_level.ante if hand.blind_level is not None else 0,
        game_format=game_format,
    )


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
