"""Evaluation and comparison of Texas Hold'em hands."""

from dataclasses import dataclass
from enum import IntEnum
from itertools import combinations

from .constants import RANKS, Card

RANK_VALUES: dict[str, int] = {rank: index + 2 for index, rank in enumerate(RANKS)}


class HandCategory(IntEnum):
    HIGH_CARD = 0
    PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8


CATEGORY_NAMES: dict[HandCategory, str] = {
    HandCategory.HIGH_CARD: "High Card",
    HandCategory.PAIR: "Pair",
    HandCategory.TWO_PAIR: "Two Pair",
    HandCategory.THREE_OF_A_KIND: "Three of a Kind",
    HandCategory.STRAIGHT: "Straight",
    HandCategory.FLUSH: "Flush",
    HandCategory.FULL_HOUSE: "Full House",
    HandCategory.FOUR_OF_A_KIND: "Four of a Kind",
    HandCategory.STRAIGHT_FLUSH: "Straight Flush",
}


@dataclass(frozen=True)
class HandEvaluation:
    """Complete result of evaluating a poker hand."""

    rank: HandCategory
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

    ranks = [card_rank(card) for card in all_cards]
    suits = [card[1] for card in all_cards]

    category, tiebreaker, flush_suit = _best_category(ranks, suits)
    cards = _select_cards(all_cards, ranks, suits, category, tiebreaker, flush_suit)

    return make_evaluation(rank=category, cards=cards, tiebreaker=tiebreaker)


def evaluate_best_of_combinations(cards: list[Card]) -> HandEvaluation:
    """Evaluate every five-card combination and keep the best one.

    This is the definition of the best hand. ``evaluate_hand`` computes the
    same result directly; this slower version is kept as its reference.
    """
    return max(
        (
            evaluate_five_cards(list(five_cards))
            for five_cards in combinations(cards, 5)
        ),
        key=HandEvaluation.comparison_key,
    )


def _best_category(
    ranks: list[int],
    suits: list[str],
) -> tuple[HandCategory, tuple[int, ...], str | None]:
    """Return the category and tiebreaker of the best five cards.

    The third value is the suit of the flush, when the best hand is one.
    """
    flush_suit = next((suit for suit in set(suits) if suits.count(suit) >= 5), None)
    flush_ranks: list[int] = []

    if flush_suit is not None:
        flush_ranks = sorted(
            (
                rank
                for rank, suit in zip(ranks, suits, strict=True)
                if suit == flush_suit
            ),
            reverse=True,
        )
        straight_flush_high = _straight_high(flush_ranks)

        if straight_flush_high is not None:
            return HandCategory.STRAIGHT_FLUSH, (straight_flush_high,), flush_suit

    counts: dict[int, int] = {}

    for rank in ranks:
        counts[rank] = counts.get(rank, 0) + 1

    distinct_ranks = sorted(counts, reverse=True)
    # The largest groups first, the highest rank first among equal groups.
    groups = sorted(counts, key=lambda rank: (counts[rank], rank), reverse=True)
    top_rank = groups[0]
    top_count = counts[top_rank]
    second_rank = groups[1]
    second_count = counts[second_rank]

    def kickers(*excluded: int) -> list[int]:
        return [rank for rank in distinct_ranks if rank not in excluded]

    if top_count == 4:
        return HandCategory.FOUR_OF_A_KIND, (top_rank, kickers(top_rank)[0]), None

    if top_count == 3 and second_count >= 2:
        return HandCategory.FULL_HOUSE, (top_rank, second_rank), None

    if flush_suit is not None:
        return HandCategory.FLUSH, tuple(flush_ranks[:5]), flush_suit

    straight_high = _straight_high(distinct_ranks)

    if straight_high is not None:
        return HandCategory.STRAIGHT, (straight_high,), None

    if top_count == 3:
        return (
            HandCategory.THREE_OF_A_KIND,
            (top_rank, *kickers(top_rank)[:2]),
            None,
        )

    if top_count == 2 and second_count == 2:
        return (
            HandCategory.TWO_PAIR,
            (top_rank, second_rank, kickers(top_rank, second_rank)[0]),
            None,
        )

    if top_count == 2:
        return HandCategory.PAIR, (top_rank, *kickers(top_rank)[:3]), None

    return HandCategory.HIGH_CARD, tuple(distinct_ranks[:5]), None


def _straight_high(ranks: list[int]) -> int | None:
    """Return the high card of the best straight among ``ranks``, if any."""
    mask = 0

    for rank in ranks:
        mask |= 1 << rank

    if mask & (1 << 14):
        mask |= 1 << 1  # The ace also plays low, in A-2-3-4-5.

    for high in range(14, 4, -1):
        window = 0b11111 << (high - 4)

        if mask & window == window:
            return high

    return None


def _select_cards(
    cards: list[Card],
    ranks: list[int],
    suits: list[str],
    category: HandCategory,
    tiebreaker: tuple[int, ...],
    flush_suit: str | None,
) -> list[Card]:
    """Pick the five cards making the best hand.

    When several sets of cards make the same hand, the earliest cards are
    kept, in their original order, like the first best combination would be.
    """
    needed: dict[int, int] = {}

    for rank, count in _ranks_of_best_hand(category, tiebreaker):
        needed[rank] = needed.get(rank, 0) + count

    selected: list[Card] = []

    for card, rank, suit in zip(cards, ranks, suits, strict=True):
        if needed.get(rank, 0) > 0 and (flush_suit is None or suit == flush_suit):
            selected.append(card)
            needed[rank] -= 1

    return selected


def _ranks_of_best_hand(
    category: HandCategory, tiebreaker: tuple[int, ...]
) -> list[tuple[int, int]]:
    """Return the (rank, count) pairs making up a hand."""
    if category in (HandCategory.STRAIGHT, HandCategory.STRAIGHT_FLUSH):
        high = tiebreaker[0]
        return [(14 if rank == 1 else rank, 1) for rank in range(high, high - 5, -1)]

    group_sizes: dict[HandCategory, tuple[int, ...]] = {
        HandCategory.FOUR_OF_A_KIND: (4, 1),
        HandCategory.FULL_HOUSE: (3, 2),
        HandCategory.THREE_OF_A_KIND: (3, 1, 1),
        HandCategory.TWO_PAIR: (2, 2, 1),
        HandCategory.PAIR: (2, 1, 1, 1),
    }
    sizes = group_sizes.get(category, (1, 1, 1, 1, 1))

    return list(zip(tiebreaker, sizes, strict=True))


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
            rank=HandCategory.STRAIGHT_FLUSH,
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
            rank=HandCategory.FOUR_OF_A_KIND,
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
                rank=HandCategory.FULL_HOUSE,
                cards=cards,
                tiebreaker=(
                    triple_rank,
                    remaining_pairs[0],
                ),
            )

    if is_flush:
        return make_evaluation(
            rank=HandCategory.FLUSH,
            cards=cards,
            tiebreaker=tuple(
                sorted_ranks,
            ),
        )

    if straight_high is not None:
        return make_evaluation(
            rank=HandCategory.STRAIGHT,
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
            rank=HandCategory.THREE_OF_A_KIND,
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
            rank=HandCategory.TWO_PAIR,
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
            rank=HandCategory.PAIR,
            cards=cards,
            tiebreaker=(
                pair_rank,
                *kickers,
            ),
        )

    return make_evaluation(
        rank=HandCategory.HIGH_CARD,
        cards=cards,
        tiebreaker=tuple(
            sorted_ranks,
        ),
    )


def make_evaluation(
    rank: HandCategory,
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

    rank = RANK_VALUES.get(card[0])

    if rank is None:
        raise ValueError(f"Invalid card rank: {card}")

    return rank


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
