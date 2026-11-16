"""A player's stats over the hands of a game, read from the hand history.

Only the immutable records of each hand are used (actions, payouts,
showdown evaluations): the ``Player`` objects are reused from hand to hand,
so their state describes the last hand only.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from backend.poker_engine.constants import ActionType, Street
from backend.poker_engine.models import Hand

VOLUNTARY_ACTIONS = (ActionType.CALL, ActionType.RAISE, ActionType.ALL_IN)
AGGRESSIVE_ACTIONS = (ActionType.RAISE, ActionType.ALL_IN)


@dataclass(frozen=True)
class PlayerSummary:
    hands_dealt: int = 0
    hands_won: int = 0
    voluntarily_played: int = 0
    raised_preflop: int = 0
    showdowns: int = 0
    showdowns_won: int = 0
    all_ins: int = 0
    biggest_pot_won: int = 0

    @property
    def vpip(self) -> float | None:
        return self._share(self.voluntarily_played)

    @property
    def pfr(self) -> float | None:
        return self._share(self.raised_preflop)

    def _share(self, count: int) -> float | None:
        return count / self.hands_dealt if self.hands_dealt else None


def summarize_player(hands: Sequence[Hand], name: str) -> PlayerSummary:
    """Stats of ``name`` over ``hands``; a hand counts when they were dealt in.

    A player dealt in always has an action in the history: an ante, a blind,
    or a decision.
    """
    dealt = won = voluntary = raised = showdowns = showdowns_won = all_ins = 0
    biggest = 0

    for hand in hands:
        own = [event for event in hand.actions if event.player == name]

        if not own:
            continue

        dealt += 1
        preflop = [event.action for event in own if event.street == Street.PREFLOP]
        voluntary += any(action in VOLUNTARY_ACTIONS for action in preflop)
        raised += any(action in AGGRESSIVE_ACTIONS for action in preflop)
        all_ins += any(event.action == ActionType.ALL_IN for event in own)
        payout = hand.payouts.get(name, 0)
        won += payout > 0
        biggest = max(biggest, payout)

        if name in hand.showdown_evaluations:
            showdowns += 1
            showdowns_won += payout > 0

    return PlayerSummary(
        hands_dealt=dealt,
        hands_won=won,
        voluntarily_played=voluntary,
        raised_preflop=raised,
        showdowns=showdowns,
        showdowns_won=showdowns_won,
        all_ins=all_ins,
        biggest_pot_won=biggest,
    )
