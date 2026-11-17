"""Orchestration of a poker game between the engine and the controllers.

``PokerGame`` advances a session one step at a time (one player action or one
street), so a user interface stays in control of the pacing and never blocks.
"""

from collections.abc import Mapping
from pathlib import Path

from backend.poker_engine.betting import apply_action
from backend.poker_engine.hand import advance_hand, start_hand
from backend.poker_engine.models import ActionEvent, Hand, Player
from backend.poker_engine.session import GameSession

from .controllers import (
    DecisionContext,
    HumanController,
    PlayerController,
    build_decision_context,
)
from .game_modes import GameMode
from .persistence import save_session


class PokerGame:
    """A poker session played by controllers (humans and bots)."""

    def __init__(
        self,
        session: GameSession,
        controllers: Mapping[str, PlayerController],
        save_path: Path | None = None,
    ) -> None:
        """Create a game.

        ``controllers`` maps every player name to its controller. When
        ``save_path`` is given, the session is saved there after each hand.
        """
        missing = [p.name for p in session.players if p.name not in controllers]

        if missing:
            raise ValueError(f"Players without a controller: {', '.join(missing)}.")

        self.session = session
        self.controllers = dict(controllers)
        self.save_path = save_path
        self.hand: Hand | None = None

    @property
    def human_name(self) -> str | None:
        """The player the user plays, if any."""
        return next((name for name, c in self.controllers.items() if c.is_human), None)

    @property
    def is_hand_in_progress(self) -> bool:
        return self.hand is not None and not self.hand.finished

    @property
    def current_player(self) -> Player | None:
        """The player expected to act, if any."""
        if self.hand is None or self.hand.finished:
            return None

        return self.hand.current_player

    @property
    def is_waiting_for_human(self) -> bool:
        """True when the next step requires a decision from the user."""
        player = self.current_player

        if player is None:
            return False

        controller = self.controllers[player.name]

        return (
            isinstance(controller, HumanController)
            and not controller.has_pending_action
        )

    def can_start_hand(self) -> bool:
        """Return True if enough players have chips to play another hand."""
        return not self.is_hand_in_progress and self.session.can_continue()

    def start_hand(self) -> Hand:
        """Start the next hand.

        Players still busted at this point are eliminated, and the button
        moves on from the previous hand.
        """
        if self.is_hand_in_progress:
            raise RuntimeError("A hand is already in progress.")

        for player in self.session.get_busted_players():
            self.session.eliminate_player(player)

        if not self.session.can_continue():
            raise RuntimeError("At least two players with chips are required.")

        if self.session.hands:
            self.session.table.move_dealer()

        self.hand = start_hand(self.session)

        return self.hand

    def step(self) -> ActionEvent | None:
        """Advance the current hand by one step.

        Executes the decision of the player to act and returns its record, or
        deals the next street / resolves the showdown and returns None.
        """
        hand = self.hand

        if hand is None or hand.finished:
            raise RuntimeError("No hand is in progress.")

        player = hand.current_player
        event = None

        if player is None:
            advance_hand(hand)
        else:
            context = self.build_context(player)
            action = self.controllers[player.name].choose_action(context)
            event = apply_action(hand, action)

        if hand.finished:
            self._on_hand_finished()

        return event

    def build_context(self, player: Player) -> DecisionContext:
        """Build the information a player is allowed to see to decide."""
        if self.hand is None:
            raise RuntimeError("No hand has been started.")

        return build_decision_context(
            hand=self.hand, player=player, big_blind=self.session.blind_level.big_blind
        )

    def _on_hand_finished(self) -> None:
        """Eliminate busted bots and save the session.

        A busted human stays seated until the next hand starts, which leaves
        time to rebuy.
        """
        for player in self.session.get_busted_players():
            if not self.controllers[player.name].is_human:
                self.session.eliminate_player(player)

        if self.save_path is not None:
            save_session(
                session=self.session,
                file_path=self.save_path,
                human=self.human_name,
                mode=GameMode.CASH,
            )
