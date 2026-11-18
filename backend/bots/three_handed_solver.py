"""Three-handed push/fold solved by Monte Carlo CFR (V2.x).

**The game.** The button, the small blind and the big blind, each with an
effective stack of ``S`` big blinds, antes possible. Every decision is
all-in or fold:

- the button shoves or folds;
- the small blind calls the button's shove or folds, or, folded to, shoves
  or folds;
- the big blind calls or folds against the button alone, the button and the
  small blind, or the small blind alone.

That makes six decision points ("information sets" per starting hand); the
small blind and the big blind each have one per situation they can face.

**The method.** With three players the equities of every trio of starting
hands (169³) are too many to tabulate as heads-up does. So each iteration
deals real cards (three hands and a board) and walks the small game tree
with the current strategies (*chance-sampling* CFR): each decision adds to
its regrets what the other action would have won on that deal, weighted by
how likely the others were to lead there. With CFR+ (regrets never below
zero) and a linearly weighted average, the average strategies converge to an
equilibrium, the more iterations the closer.
"""

import random
from dataclasses import dataclass
from enum import IntEnum

from backend.application.ranges import ALL_LABELS, label_combos
from backend.poker_engine.constants import RANKS, SUITS, Card
from backend.poker_engine.hand_evaluator import evaluate_rank

HANDS: tuple[str, ...] = ALL_LABELS
DECK: tuple[Card, ...] = tuple(rank + suit for rank in RANKS for suit in SUITS)
SMALL_BLIND = 0.5
BIG_BLIND = 1.0
BUTTON, SMALL, BIG = 0, 1, 2
CLASS_OF: dict[tuple[Card, Card], int] = {
    combo: index
    for index, label in enumerate(HANDS)
    for first, second in label_combos(label)
    for combo in ((first, second), (second, first))
}


Values = tuple[float, float, float]
"""The net result of the button, the small blind and the big blind."""


class Spot(IntEnum):
    """The six decisions; the first action is the aggressive one."""

    BUTTON_SHOVES = 0
    SMALL_BLIND_CALLS = 1
    """Against the button's shove."""
    SMALL_BLIND_SHOVES = 2
    """Folded to it."""
    BIG_BLIND_CALLS_BUTTON = 3
    BIG_BLIND_CALLS_BOTH = 4
    BIG_BLIND_CALLS_SMALL_BLIND = 5


SEATS = {
    Spot.BUTTON_SHOVES: BUTTON,
    Spot.SMALL_BLIND_CALLS: SMALL,
    Spot.SMALL_BLIND_SHOVES: SMALL,
    Spot.BIG_BLIND_CALLS_BUTTON: BIG,
    Spot.BIG_BLIND_CALLS_BOTH: BIG,
    Spot.BIG_BLIND_CALLS_SMALL_BLIND: BIG,
}
"""Who decides at each spot."""


@dataclass(frozen=True)
class ThreeHandedStrategy:
    """How often each hand takes the aggressive action at each spot."""

    stack: float
    antes: tuple[float, float, float]
    spots: tuple[tuple[float, ...], ...]
    """``spots[spot][hand]``: the probability of shoving or calling."""

    def range_at(self, spot: Spot, threshold: float = 0.5) -> frozenset[str]:
        return frozenset(
            hand
            for hand, p in zip(HANDS, self.spots[spot], strict=True)
            if p >= threshold
        )


def solve_three_handed(
    stack: float,
    iterations: int,
    seed: int,
    antes: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> ThreeHandedStrategy:
    """Chance-sampling CFR+ over ``iterations`` random deals."""
    rng = random.Random(seed)
    posted = (antes[0], SMALL_BLIND + antes[1], BIG_BLIND + antes[2])
    size = len(HANDS)
    shove_regret = [[0.0] * size for _ in Spot]
    fold_regret = [[0.0] * size for _ in Spot]
    totals = [[0.0] * size for _ in Spot]
    seen = [[0.0] * size for _ in range(3)]
    """The iteration weights each hand received in each seat."""

    def strategy(spot: Spot, hand: int) -> float:
        aggressive, passive = shove_regret[spot][hand], fold_regret[spot][hand]
        total = aggressive + passive

        return aggressive / total if total > 0 else 0.5

    def update(
        spot: Spot,
        hand: int,
        reach: float,
        probability: float,
        values: tuple[float, float],
    ) -> None:
        """Add the regrets of one decision (aggressive and passive values)."""
        shove, fold = values
        average = probability * shove + (1 - probability) * fold
        shove_regret[spot][hand] = max(
            0.0, shove_regret[spot][hand] + reach * (shove - average)
        )
        fold_regret[spot][hand] = max(
            0.0, fold_regret[spot][hand] + reach * (fold - average)
        )

    for iteration in range(1, iterations + 1):
        cards = rng.sample(DECK, 11)
        hands = (
            CLASS_OF[cards[0], cards[1]],
            CLASS_OF[cards[2], cards[3]],
            CLASS_OF[cards[4], cards[5]],
        )
        board = cards[6:]
        ranks = (
            evaluate_rank([cards[0], cards[1], *board]),
            evaluate_rank([cards[2], cards[3], *board]),
            evaluate_rank([cards[4], cards[5], *board]),
        )

        p = strategy(Spot.BUTTON_SHOVES, hands[BUTTON])
        q_call = strategy(Spot.SMALL_BLIND_CALLS, hands[SMALL])
        q_shove = strategy(Spot.SMALL_BLIND_SHOVES, hands[SMALL])
        r_button = strategy(Spot.BIG_BLIND_CALLS_BUTTON, hands[BIG])
        r_both = strategy(Spot.BIG_BLIND_CALLS_BOTH, hands[BIG])
        r_small = strategy(Spot.BIG_BLIND_CALLS_SMALL_BLIND, hands[BIG])

        button_and_big = _result((BUTTON, BIG), ranks, posted, stack)
        button_alone = _result((BUTTON,), ranks, posted, stack)
        everyone = _result((BUTTON, SMALL, BIG), ranks, posted, stack)
        button_and_small = _result((BUTTON, SMALL), ranks, posted, stack)
        small_and_big = _result((SMALL, BIG), ranks, posted, stack)
        small_alone = _result((SMALL,), ranks, posted, stack)
        big_alone = _result((BIG,), ranks, posted, stack)

        big_vs_button = _mix(r_button, button_and_big, button_alone)
        big_vs_both = _mix(r_both, everyone, button_and_small)
        big_vs_small = _mix(r_small, small_and_big, small_alone)
        small_vs_shove = _mix(q_call, big_vs_both, big_vs_button)
        small_open = _mix(q_shove, big_vs_small, big_alone)

        update(
            Spot.BUTTON_SHOVES,
            hands[BUTTON],
            1.0,
            p,
            (small_vs_shove[BUTTON], small_open[BUTTON]),
        )
        update(
            Spot.SMALL_BLIND_CALLS,
            hands[SMALL],
            p,
            q_call,
            (big_vs_both[SMALL], big_vs_button[SMALL]),
        )
        update(
            Spot.SMALL_BLIND_SHOVES,
            hands[SMALL],
            1 - p,
            q_shove,
            (big_vs_small[SMALL], big_alone[SMALL]),
        )
        update(
            Spot.BIG_BLIND_CALLS_BUTTON,
            hands[BIG],
            p * (1 - q_call),
            r_button,
            (button_and_big[BIG], button_alone[BIG]),
        )
        update(
            Spot.BIG_BLIND_CALLS_BOTH,
            hands[BIG],
            p * q_call,
            r_both,
            (everyone[BIG], button_and_small[BIG]),
        )
        update(
            Spot.BIG_BLIND_CALLS_SMALL_BLIND,
            hands[BIG],
            (1 - p) * q_shove,
            r_small,
            (small_and_big[BIG], small_alone[BIG]),
        )

        for seat in (BUTTON, SMALL, BIG):
            seen[seat][hands[seat]] += iteration

        for spot, probability, seat in (
            (Spot.BUTTON_SHOVES, p, BUTTON),
            (Spot.SMALL_BLIND_CALLS, q_call, SMALL),
            (Spot.SMALL_BLIND_SHOVES, q_shove, SMALL),
            (Spot.BIG_BLIND_CALLS_BUTTON, r_button, BIG),
            (Spot.BIG_BLIND_CALLS_BOTH, r_both, BIG),
            (Spot.BIG_BLIND_CALLS_SMALL_BLIND, r_small, BIG),
        ):
            totals[spot][hands[seat]] += iteration * probability

    return ThreeHandedStrategy(
        stack=stack,
        antes=antes,
        spots=tuple(
            tuple(
                total / weight if weight else 0.0
                for total, weight in zip(totals[spot], seen[SEATS[spot]], strict=True)
            )
            for spot in Spot
        ),
    )


def _mix(probability: float, aggressive: Values, passive: Values) -> Values:
    return (
        probability * aggressive[0] + (1 - probability) * passive[0],
        probability * aggressive[1] + (1 - probability) * passive[1],
        probability * aggressive[2] + (1 - probability) * passive[2],
    )


def _result(
    players: tuple[int, ...],
    ranks: tuple[object, object, object],
    posted: tuple[float, float, float],
    stack: float,
) -> Values:
    """Everyone's net result when ``players`` are all-in and the others
    folded (losing what they posted); one player alone takes the blinds."""
    dead = sum(posted[seat] for seat in range(3) if seat not in players)
    values = [-posted[seat] for seat in range(3)]

    if len(players) == 1:
        winner = players[0]
        values[winner] = dead
        return values[0], values[1], values[2]

    pot = stack * len(players) + dead
    best = max(ranks[seat] for seat in players)  # type: ignore[type-var]
    winners = [seat for seat in players if ranks[seat] == best]

    for seat in players:
        values[seat] = (pot / len(winners) if seat in winners else 0.0) - stack

    return values[0], values[1], values[2]
