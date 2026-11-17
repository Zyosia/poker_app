"""What a strategy bot believes about its opponents.

**Live statistics** (``StatsBook``): from the public actions of every hand
played at the table, the adaptive bot counts each opponent's VPIP (hands
played voluntarily), PFR (pre-flop raises), aggression factor (bets and
raises per call after the flop) and how often they fold to a bet. Until an
opponent has played enough hands, the figures lean on those of a typical
player (``PRIOR``): every count starts with ``PRIOR_HANDS`` imaginary hands.

**Ranges** (``starting_range``, ``OpponentRange``): every opponent starts
with all the hands they could hold (none of the cards the bot sees), then
each action narrows it:

- *Pre-flop*, a raise keeps the strongest hands of an opening range, a
  re-raise far fewer; a call keeps a middle band (the very best hands would
  have re-raised); a limp or a check keeps a wide band.
- *After the flop*, each hand of the range is rated on the board at the time
  of the action (``basic_bot.postflop_strength``): a bet or raise keeps the
  made hands and a few bluffs, a call drops most of the air, a check makes
  the strongest hands less likely (they would often have bet).

The bots only read public information: actions, the board and their own
cards, never an opponent's hidden cards.
"""

import random
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from backend.application.ranges import ALL_LABELS, Combo, label_combos
from backend.poker_engine.constants import ActionType, Card, Street
from backend.poker_engine.models import ActionEvent

from .basic_bot import postflop_strength
from .push_fold import PERCENT_BEFORE

AGGRESSIVE = frozenset({ActionType.RAISE, ActionType.ALL_IN})
VOLUNTARY = frozenset({ActionType.CALL, ActionType.RAISE, ActionType.ALL_IN})
BLIND_POSTS = frozenset({"post_sb", "post_bb", "post_ante"})


@dataclass(frozen=True)
class PlayerTendencies:
    """How a player plays, as frequencies."""

    vpip: float
    pfr: float
    aggression: float
    """Bets and raises per call after the flop."""
    fold_to_bet: float


PRIOR = PlayerTendencies(vpip=0.28, pfr=0.18, aggression=2.0, fold_to_bet=0.45)
"""A typical player, before anything is known."""
PRIOR_HANDS = 20
"""Weight of the prior, in hands (or actions for the post-flop figures)."""


@dataclass
class OpponentStats:
    """Counts of one opponent's actions."""

    hands: int = 0
    vpip_hands: int = 0
    pfr_hands: int = 0
    aggressive_actions: int = 0
    calls: int = 0
    bets_faced: int = 0
    folds_to_bet: int = 0

    def tendencies(self) -> PlayerTendencies:
        """The counts blended with ``PRIOR``."""
        return PlayerTendencies(
            vpip=_blend(self.vpip_hands, self.hands, PRIOR.vpip),
            pfr=_blend(self.pfr_hands, self.hands, PRIOR.pfr),
            aggression=(self.aggressive_actions + PRIOR.aggression * PRIOR_HANDS)
            / (self.calls + PRIOR_HANDS),
            fold_to_bet=_blend(self.folds_to_bet, self.bets_faced, PRIOR.fold_to_bet),
        )


def _blend(count: int, total: int, prior: float) -> float:
    return (count + prior * PRIOR_HANDS) / (total + PRIOR_HANDS)


@dataclass
class StatsBook:
    """The statistics of every opponent seen at the table."""

    players: dict[str, OpponentStats] = field(default_factory=dict)

    def tendencies(self, name: str) -> PlayerTendencies:
        stats = self.players.get(name)

        return PRIOR if stats is None else stats.tendencies()

    def record_hand(self, actions: Sequence[ActionEvent]) -> None:
        """Count the actions of one finished hand."""
        seen: set[str] = set()
        played: set[str] = set()
        raised: set[str] = set()
        street = Street.PREFLOP
        current_bet = 0

        for event in actions:
            stats = self.players.setdefault(event.player, OpponentStats())
            seen.add(event.player)

            if event.street != street:
                street, current_bet = event.street, 0

            if event.action in BLIND_POSTS:
                current_bet = max(current_bet, event.current_bet_after)
                continue

            if street == Street.PREFLOP:
                if event.action in VOLUNTARY:
                    played.add(event.player)
                if event.action in AGGRESSIVE:
                    raised.add(event.player)
            else:
                facing_bet = current_bet > event.bet_before

                if event.action in AGGRESSIVE:
                    stats.aggressive_actions += 1
                elif event.action == ActionType.CALL:
                    stats.calls += 1

                if facing_bet:
                    stats.bets_faced += 1
                    stats.folds_to_bet += event.action == ActionType.FOLD

            current_bet = max(current_bet, event.current_bet_after)

        for name in seen:
            stats = self.players[name]
            stats.hands += 1
            stats.vpip_hands += name in played
            stats.pfr_hands += name in raised


# --- Ranges ------------------------------------------------------------------------

CALLER_STRONG_WEIGHT = 0.3
"""A caller's hands that would have re-raised stay possible, less likely."""
LIMP_PERCENT = 55.0
CHECKED_STRONG_WEIGHT = 0.5
"""The big blind checking keeps any hand, the strongest less likely."""
CHECKED_STRONG_PERCENT = 10.0
RERAISE_PERCENT = 6.0
"""A re-raise (three-bet) keeps about the strongest 6% of hands."""
FOUR_BET_PERCENT = 3.0

BET_STRENGTH = 0.5
"""After the flop, a bet or raise mostly holds a pair or better."""
CALL_STRENGTH = 0.3
"""A call mostly holds a pair or a draw."""
SLOWPLAY_STRENGTH = 0.75
CHECKED_WEIGHT = 0.6
"""Weight left to the strong hands of a player who checks."""
CALL_AIR_WEIGHT = 0.3
MIN_BLUFF_WEIGHT = 0.05
BLUFF_WEIGHT_PER_AGGRESSION = 0.06
MAX_BLUFF_WEIGHT = 0.45
POSTFLOP_RANGE_SIZE = 160
"""Hands kept per opponent once the flop is dealt (a weighted sample)."""


def starting_range(
    preflop_actions: Iterable[ActionEvent],
    name: str,
    open_percent: float,
    vpip_percent: float,
) -> dict[str, float]:
    """The weight of each starting hand after the pre-flop actions of
    ``name``. ``open_percent`` is their opening range (percent of hands)
    from their seat, ``vpip_percent`` the widest range they play."""
    raises_before = 0
    weights = dict.fromkeys(ALL_LABELS, 1.0)

    for event in preflop_actions:
        if event.action in BLIND_POSTS:
            continue

        if event.player == name:
            if event.action in AGGRESSIVE:
                top = (open_percent, RERAISE_PERCENT)[min(raises_before, 1)]
                top = FOUR_BET_PERCENT if raises_before >= 2 else top
                band = _band(0.0, top, 1.0)
            elif event.action == ActionType.CALL:
                widest = max(LIMP_PERCENT if raises_before == 0 else 0.0, vpip_percent)
                band = _band(RERAISE_PERCENT, widest, CALLER_STRONG_WEIGHT)
            elif event.action == ActionType.CHECK:
                band = _band(CHECKED_STRONG_PERCENT, 100.0, CHECKED_STRONG_WEIGHT)
            else:
                band = weights

            if band is not weights:
                weights = {
                    label: weight * band[label]
                    for label, weight in weights.items()
                    if label in band
                }

        if event.action in AGGRESSIVE:
            raises_before += 1

    return weights


def _band(strongest: float, widest: float, strong_weight: float) -> dict[str, float]:
    """The hands from the ``strongest`` to the ``widest`` percent (weight 1);
    stronger ones weigh ``strong_weight``, weaker ones nothing."""
    weights: dict[str, float] = {}

    for label in ALL_LABELS:
        before = PERCENT_BEFORE[label]

        if before < strongest:
            weights[label] = strong_weight
        elif before < widest:
            weights[label] = 1.0

    return weights


def bluff_weight(tendencies: PlayerTendencies) -> float:
    """How likely a bet holds a weak hand: more with aggressive players."""
    weight = MIN_BLUFF_WEIGHT + BLUFF_WEIGHT_PER_AGGRESSION * tendencies.aggression

    return min(weight, MAX_BLUFF_WEIGHT)


@dataclass
class OpponentRange:
    """The hands an opponent may hold, with a weight each."""

    combos: list[Combo]
    weights: list[float]

    @classmethod
    def from_starting_hands(
        cls,
        hands: dict[str, float],
        dead: set[Card],
        rng: random.Random,
        size: int = POSTFLOP_RANGE_SIZE,
    ) -> "OpponentRange":
        """Every combination of the hands that avoids the ``dead`` cards; a
        weighted sample of ``size`` of them when there are more."""
        combos: list[Combo] = []
        weights: list[float] = []

        for label, weight in hands.items():
            for combo in label_combos(label):
                if combo[0] not in dead and combo[1] not in dead:
                    combos.append(combo)
                    weights.append(weight)

        if not combos:
            raise ValueError("No hand is left in the range.")

        if len(combos) > size:
            combos = rng.choices(combos, weights=weights, k=size)
            weights = [1.0] * size

        return cls(combos, weights)

    def narrow(
        self,
        action: str,
        board: tuple[Card, ...],
        tendencies: PlayerTendencies,
    ) -> None:
        """Reweigh the hands after a post-flop action on ``board``."""
        if action in AGGRESSIVE:
            weak = bluff_weight(tendencies)
            self._reweigh(board, lambda s: 1.0 if s >= BET_STRENGTH else weak)
        elif action == ActionType.CALL:
            self._reweigh(
                board, lambda s: 1.0 if s >= CALL_STRENGTH else CALL_AIR_WEIGHT
            )
        elif action == ActionType.CHECK:
            self._reweigh(
                board, lambda s: CHECKED_WEIGHT if s >= SLOWPLAY_STRENGTH else 1.0
            )

    def remove(self, dead: set[Card]) -> None:
        """Drop the hands holding a card now known elsewhere (the board)."""
        kept = [
            (combo, weight)
            for combo, weight in zip(self.combos, self.weights, strict=True)
            if combo[0] not in dead and combo[1] not in dead
        ]

        if kept:
            self.combos = [combo for combo, _ in kept]
            self.weights = [weight for _, weight in kept]

    def strengths(self, board: tuple[Card, ...]) -> list[float]:
        return [postflop_strength(combo, board) for combo in self.combos]

    def _reweigh(
        self, board: tuple[Card, ...], factor: Callable[[float], float]
    ) -> None:
        self.weights = [
            weight * factor(strength)
            for weight, strength in zip(
                self.weights, self.strengths(board), strict=True
            )
        ]
