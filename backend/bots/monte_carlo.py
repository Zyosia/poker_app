"""Monte Carlo showdowns against the opponents' ranges.

A strategy bot does not know its opponents' cards, only their ranges
(``opponent_model``). It deals random hands from those ranges (each in
proportion to its weight, never a card it can see) and the rest of the
board, a few hundred times, and keeps each deal: who would win, and how
strong each opponent's hand is now (which decides whether they would call a
bet). From the same deals it reads its equity against the whole range and
against the part of it that would call a bet of a given size.

It is the equity calculator's method (V1.1) applied inside a decision, with
an RNG of the bot's own: the game's cards are never touched.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import accumulate

from backend.application.ranges import Combo
from backend.poker_engine.constants import RANKS, SUITS, Card
from backend.poker_engine.hand_evaluator import evaluate_rank

from .opponent_model import OpponentRange

DECK: tuple[Card, ...] = tuple(rank + suit for rank in RANKS for suit in SUITS)
BOARD_SIZE = 5
MAX_ATTEMPTS = 20
"""Draws allowed to find hands that do not share a card, for one deal."""

Rank = tuple[int, tuple[int, ...]]


@dataclass(frozen=True)
class Showdown:
    """One random deal: the bot's final hand and each opponent's."""

    hero: Rank
    opponents: tuple[tuple[Rank, float], ...]
    """Each opponent's final hand and current strength (0 to 1), in the
    order of the ranges given."""


def deal_showdowns(
    hole_cards: tuple[Card, ...],
    board: tuple[Card, ...],
    ranges: Sequence[OpponentRange],
    strengths: Sequence[Sequence[float]],
    count: int,
    rng: random.Random,
) -> list[Showdown]:
    """``count`` random deals (fewer if the ranges rarely fit together).

    ``strengths[i][k]`` is the current strength of the ``k``-th hand of
    ``ranges[i]``.
    """
    known = {*hole_cards, *board}
    deck = [card for card in DECK if card not in known]
    cumulative = [list(accumulate(r.weights)) for r in ranges]
    indexes = [range(len(r.combos)) for r in ranges]
    missing = BOARD_SIZE - len(board)
    drawn = missing + 2 * len(ranges)
    """Enough cards for the board whatever the opponents hold."""
    showdowns: list[Showdown] = []
    # On the river the board is complete: each hand is evaluated once.
    river_hero = evaluate_rank([*hole_cards, *board]) if not missing else None
    river_ranks: dict[Combo, Rank] = {}

    for _ in range(count):
        picks = _pick_hands(ranges, cumulative, indexes, known, rng)

        if picks is None:
            continue

        combos = [ranges[i].combos[k] for i, k in enumerate(picks)]

        if river_hero is not None:
            hero = river_hero
            ranks = [_river_rank(combo, board, river_ranks) for combo in combos]
        else:
            held = {card for combo in combos for card in combo}
            extra = [card for card in rng.sample(deck, drawn) if card not in held]
            final_board = [*board, *extra[:missing]]
            hero = evaluate_rank([*hole_cards, *final_board])
            ranks = [evaluate_rank([*combo, *final_board]) for combo in combos]

        opponents = tuple(
            (rank, strengths[i][k])
            for (i, k), rank in zip(enumerate(picks), ranks, strict=True)
        )
        showdowns.append(Showdown(hero, opponents))

    return showdowns


def _river_rank(
    combo: Combo, board: tuple[Card, ...], ranks: dict[Combo, Rank]
) -> Rank:
    rank = ranks.get(combo)

    if rank is None:
        rank = evaluate_rank([*combo, *board])
        ranks[combo] = rank

    return rank


def _pick_hands(
    ranges: Sequence[OpponentRange],
    cumulative: list[list[float]],
    indexes: list[range],
    known: set[Card],
    rng: random.Random,
) -> list[int] | None:
    for _ in range(MAX_ATTEMPTS):
        used = set(known)
        picks: list[int] = []

        for i, opponent in enumerate(ranges):
            if cumulative[i][-1] <= 0:
                return None

            k = rng.choices(indexes[i], cum_weights=cumulative[i])[0]
            combo = opponent.combos[k]

            if combo[0] in used or combo[1] in used:
                break

            used.update(combo)
            picks.append(k)
        else:
            return picks

    return None


def share_against(showdown: Showdown, continuing: Sequence[int]) -> float:
    """The bot's share of the pot against the opponents ``continuing``."""
    best = max(showdown.opponents[i][0] for i in continuing)

    if showdown.hero > best:
        return 1.0

    if showdown.hero < best:
        return 0.0

    tied = sum(1 for i in continuing if showdown.opponents[i][0] == best)

    return 1.0 / (tied + 1)


def equity(showdowns: Sequence[Showdown]) -> float:
    """The bot's average share against every opponent."""
    if not showdowns:
        return 0.0

    everyone = range(len(showdowns[0].opponents))

    return sum(share_against(s, everyone) for s in showdowns) / len(showdowns)
