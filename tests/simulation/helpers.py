"""Helpers shared by the simulation tests."""

from collections.abc import Callable, Iterable

from backend.application.controllers import DecisionContext, PlayerController
from backend.poker_engine.actions import Action
from backend.poker_engine.constants import ActionType, Card
from backend.poker_engine.deck import Deck
from backend.simulation.events import HandObserver

AttachObserver = Callable[[HandObserver], None]


class ScriptedBot(PlayerController):
    """Plays a fixed list of actions, given as ("raise", 30) or ("call", None)."""

    def __init__(self, actions: Iterable[tuple[str, int | None]]) -> None:
        self._actions = iter(actions)

    def choose_action(self, context: DecisionContext) -> Action:
        action_type, amount = next(self._actions)

        return Action(type=ActionType(action_type), amount=amount)


def stacked_deck(cards_in_deal_order: list[Card]) -> Deck:
    """A deck that deals the given cards in order (hole cards, burns, board)."""
    deck = Deck()
    deck.cards = list(reversed(cards_in_deal_order))

    return deck
