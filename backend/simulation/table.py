"""A table of bots driving the engine one step at a time."""

from collections.abc import Mapping, Sequence

from backend.application.controllers import PlayerController, build_decision_context
from backend.poker_engine.betting import apply_action
from backend.poker_engine.deck import Deck
from backend.poker_engine.hand import advance_hand, start_hand
from backend.poker_engine.models import ActionEvent, Hand, Player
from backend.poker_engine.session import GameConfig, GameSession

from .events import HandObserver


class ArenaTable:
    """Bots seated at one table, playing hands through the engine.

    Unlike ``PokerGame`` it never saves anything, and it notifies observers
    of every step instead of relying on the hand history.
    """

    def __init__(
        self,
        seat_names: Sequence[str],
        controllers: Mapping[str, PlayerController],
        game_config: GameConfig,
        observers: Sequence[HandObserver] = (),
    ) -> None:
        players = [
            Player(name=name, stack=game_config.starting_stack) for name in seat_names
        ]
        self.session = GameSession(players=players, config=game_config)
        self.controllers = controllers
        self.observers = list(observers)
        self.hand: Hand | None = None
        self.stacks_before: dict[str, int] = {}

    @property
    def players(self) -> list[Player]:
        """Seats in clockwise order."""
        return self.session.players

    def start_hand(self, deck: Deck) -> Hand:
        """Deal a new hand from ``deck`` with the current stacks and button."""
        # Finished hands are not kept: over millions of hands they would
        # exhaust the memory.
        self.session.hands.clear()
        self.stacks_before = {
            player.name: player.stack
            for player in self.session.get_players_with_chips()
        }

        hand = start_hand(session=self.session, deck=deck)
        self.hand = hand

        for observer in self.observers:
            observer.on_hand_start(hand)

        self._notify_if_finished(hand)

        return hand

    def step(self) -> ActionEvent | None:
        """Play the next decision, or deal the next street.

        Returns the action played, or None when a street was dealt or the
        showdown resolved.
        """
        hand = self.hand

        if hand is None or hand.finished:
            raise RuntimeError("No hand is in progress.")

        player = hand.current_player
        event = None

        if player is None:
            advance_hand(hand)

            if not hand.finished:
                for observer in self.observers:
                    observer.on_street(hand)
        else:
            context = build_decision_context(
                hand=hand, player=player, big_blind=self.session.config.big_blind
            )
            action = self.controllers[player.name].choose_action(context)
            event = apply_action(hand, action)

            for observer in self.observers:
                observer.on_action(hand, event)

        self._notify_if_finished(hand)

        return event

    def play_hand(self, deck: Deck) -> Hand:
        """Play a complete hand."""
        hand = self.start_hand(deck)

        while not hand.finished:
            self.step()

        return hand

    def _notify_if_finished(self, hand: Hand) -> None:
        if hand.finished:
            for observer in self.observers:
                observer.on_hand_end(hand, self.stacks_before)
