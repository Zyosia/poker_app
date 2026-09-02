# game/hand_evaluator.py

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .constants import RANKS, Card

CATEGORY_HIGH_CARD = 0
CATEGORY_PAIR = 1
CATEGORY_TWO_PAIR = 2
CATEGORY_THREE_OF_A_KIND = 3
CATEGORY_STRAIGHT = 4
CATEGORY_FLUSH = 5
CATEGORY_FULL_HOUSE = 6
CATEGORY_FOUR_OF_A_KIND = 7
CATEGORY_STRAIGHT_FLUSH = 8


CATEGORY_NAMES: dict[int, str] = {
    CATEGORY_HIGH_CARD: "High Card",
    CATEGORY_PAIR: "Pair",
    CATEGORY_TWO_PAIR: "Two Pair",
    CATEGORY_THREE_OF_A_KIND: "Three of a Kind",
    CATEGORY_STRAIGHT: "Straight",
    CATEGORY_FLUSH: "Flush",
    CATEGORY_FULL_HOUSE: "Full House",
    CATEGORY_FOUR_OF_A_KIND: "Four of a Kind",
    CATEGORY_STRAIGHT_FLUSH: "Straight Flush",
}


@dataclass(frozen=True)
class HandEvaluation:
    """Complete result of evaluating a poker hand."""

    rank: int
    name: str
    cards: tuple[Card, ...]
    tiebreaker: tuple[int, ...]

    def comparison_key(self) -> tuple[int, ...]:
        """
        Return the value used to compare two evaluations.

        Category is compared first, then all tie-break values.
        """

        return (
            self.rank,
            *self.tiebreaker,
        )


def evaluate_hand(
    hole_cards: list[Card],
    community_cards: list[Card],
) -> HandEvaluation:
    """
    Evaluate the best possible Texas Hold'em hand.

    The player can use any five cards among their hole cards
    and the community cards.
    """

    all_cards = hole_cards + community_cards

    if len(all_cards) < 5:
        raise ValueError("At least five cards are required to evaluate a poker hand.")

    if len(all_cards) > 7:
        raise ValueError(
            "A Texas Hold'em hand cannot contain more than seven available cards."
        )

    evaluations = [
        evaluate_five_cards(
            list(five_cards),
        )
        for five_cards in combinations(
            all_cards,
            5,
        )
    ]

    return max(
        evaluations,
        key=HandEvaluation.comparison_key,
    )


def evaluate_five_cards(
    cards: list[Card],
) -> HandEvaluation:
    """Evaluate exactly five cards."""

    if len(cards) != 5:
        raise ValueError("Exactly five cards are required.")

    ranks = [card_rank(card) for card in cards]

    suits = [card_suit(card) for card in cards]

    sorted_ranks = sorted(
        ranks,
        reverse=True,
    )

    counts: dict[int, int] = {}

    for rank in ranks:
        counts[rank] = counts.get(rank, 0) + 1

    straight_high = get_straight_high(ranks)

    is_flush = len(set(suits)) == 1

    if is_flush and straight_high is not None:
        return make_evaluation(
            rank=CATEGORY_STRAIGHT_FLUSH,
            cards=cards,
            tiebreaker=(straight_high,),
        )

    four_rank = next(
        (rank for rank, count in counts.items() if count == 4),
        None,
    )

    if four_rank is not None:
        kicker = max(rank for rank in ranks if rank != four_rank)

        return make_evaluation(
            rank=CATEGORY_FOUR_OF_A_KIND,
            cards=cards,
            tiebreaker=(
                four_rank,
                kicker,
            ),
        )

    triple_ranks = sorted(
        (rank for rank, count in counts.items() if count == 3),
        reverse=True,
    )

    pair_ranks = sorted(
        (rank for rank, count in counts.items() if count >= 2),
        reverse=True,
    )

    if triple_ranks:
        triple_rank = triple_ranks[0]

        remaining_pairs = [rank for rank in pair_ranks if rank != triple_rank]

        if remaining_pairs:
            return make_evaluation(
                rank=CATEGORY_FULL_HOUSE,
                cards=cards,
                tiebreaker=(
                    triple_rank,
                    remaining_pairs[0],
                ),
            )

    if is_flush:
        return make_evaluation(
            rank=CATEGORY_FLUSH,
            cards=cards,
            tiebreaker=tuple(
                sorted_ranks,
            ),
        )

    if straight_high is not None:
        return make_evaluation(
            rank=CATEGORY_STRAIGHT,
            cards=cards,
            tiebreaker=(straight_high,),
        )

    if triple_ranks:
        triple_rank = triple_ranks[0]

        kickers = sorted(
            (rank for rank in ranks if rank != triple_rank),
            reverse=True,
        )

        return make_evaluation(
            rank=CATEGORY_THREE_OF_A_KIND,
            cards=cards,
            tiebreaker=(
                triple_rank,
                *kickers,
            ),
        )

    pairs = [rank for rank, count in counts.items() if count == 2]

    pairs.sort(reverse=True)

    if len(pairs) >= 2:
        high_pair = pairs[0]
        low_pair = pairs[1]

        kicker = max(
            rank
            for rank in ranks
            if rank
            not in {
                high_pair,
                low_pair,
            }
        )

        return make_evaluation(
            rank=CATEGORY_TWO_PAIR,
            cards=cards,
            tiebreaker=(
                high_pair,
                low_pair,
                kicker,
            ),
        )

    if len(pairs) == 1:
        pair_rank = pairs[0]

        kickers = sorted(
            (rank for rank in ranks if rank != pair_rank),
            reverse=True,
        )

        return make_evaluation(
            rank=CATEGORY_PAIR,
            cards=cards,
            tiebreaker=(
                pair_rank,
                *kickers,
            ),
        )

    return make_evaluation(
        rank=CATEGORY_HIGH_CARD,
        cards=cards,
        tiebreaker=tuple(
            sorted_ranks,
        ),
    )


def make_evaluation(
    rank: int,
    cards: list[Card],
    tiebreaker: tuple[int, ...],
) -> HandEvaluation:
    """Create a HandEvaluation."""

    name = CATEGORY_NAMES[rank]

    return HandEvaluation(
        rank=rank,
        name=name,
        cards=tuple(cards),
        tiebreaker=tiebreaker,
    )


def card_rank(
    card: Card,
) -> int:
    """Return the numerical rank of a card."""

    if len(card) != 2:
        raise ValueError(f"Invalid card: {card}")

    rank = card[0]

    try:
        return RANKS.index(rank) + 2
    except ValueError as exc:
        raise ValueError(f"Invalid card rank: {card}") from exc


def card_suit(
    card: Card,
) -> str:
    """Return the suit of a card."""

    if len(card) != 2:
        raise ValueError(f"Invalid card: {card}")

    return card[1]


def get_straight_high(
    ranks: list[int],
) -> int | None:
    """
    Return the highest card of a straight.

    Ace-low straight A-2-3-4-5 returns 5.
    """

    unique_ranks = set(ranks)

    if {
        14,
        2,
        3,
        4,
        5,
    }.issubset(unique_ranks):
        return 5

    sorted_unique = sorted(
        unique_ranks,
        reverse=True,
    )

    for index in range(len(sorted_unique) - 4):
        window = sorted_unique[index : index + 5]

        if window[0] - window[4] == 4:
            return window[0]

    return None
