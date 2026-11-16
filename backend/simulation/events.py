"""Lightweight notifications fed by the simulation to statistics collectors.

Collectors see every step of every hand as it happens, so they work without
keeping a full hand history.
"""

from collections.abc import Mapping

from backend.poker_engine.models import ActionEvent, Hand


class HandObserver:
    """Receives the steps of the simulated hands. Every method is optional."""

    def on_hand_start(self, hand: Hand) -> None:
        """The blinds are posted and the hole cards dealt."""

    def on_action(self, hand: Hand, event: ActionEvent) -> None:
        """A player acted; ``event`` is the engine's record of the action."""

    def on_street(self, hand: Hand) -> None:
        """A new street was dealt (``hand.street``)."""

    def on_hand_end(self, hand: Hand, stacks_before: Mapping[str, int]) -> None:
        """The hand is over; ``stacks_before`` holds the stacks of the players
        dealt in, as they were before the blinds."""
