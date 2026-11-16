"""The direct evaluator must match the best-of-all-combinations definition.

Both the hand value and the five cards chosen are compared, on random hands
and on hands drawn from reduced decks that make rare categories frequent.
"""

import random

import pytest

from backend.poker_engine.constants import RANKS, SUITS, Card
from backend.poker_engine.hand_evaluator import (
    HandCategory,
    evaluate_best_of_combinations,
    evaluate_hand,
)

FULL_DECK = [rank + suit for rank in RANKS for suit in SUITS]

REDUCED_DECKS: dict[str, list[Card]] = {
    # Few ranks: pairs, trips, full houses and quads everywhere.
    "few ranks": [rank + suit for rank in "AK72" for suit in SUITS],
    # Few suits: flushes and straight flushes are common.
    "two suits": [rank + suit for rank in RANKS for suit in "HS"],
    # Connected ranks, including the ace-low straight.
    "wheel and broadway": [rank + suit for rank in "A2345TJQK" for suit in SUITS],
}


def assert_same_evaluation(cards: list[Card]) -> None:
    assert evaluate_hand(cards[:2], cards[2:]) == evaluate_best_of_combinations(cards)


@pytest.mark.parametrize("card_count", [5, 6, 7])
def test_random_hands_match_the_reference(card_count: int) -> None:
    rng = random.Random(card_count)

    for _ in range(3000):
        assert_same_evaluation(rng.sample(FULL_DECK, card_count))


@pytest.mark.parametrize("deck_name", REDUCED_DECKS)
@pytest.mark.parametrize("card_count", [5, 6, 7])
def test_hands_from_reduced_decks_match_the_reference(
    deck_name: str, card_count: int
) -> None:
    deck = REDUCED_DECKS[deck_name]
    rng = random.Random(f"{deck_name}-{card_count}")

    for _ in range(1500):
        assert_same_evaluation(rng.sample(deck, card_count))


def test_reduced_decks_reach_every_category() -> None:
    rng = random.Random(0)
    seen: set[HandCategory] = set()

    for deck in REDUCED_DECKS.values():
        for _ in range(1500):
            cards = rng.sample(deck, 7)
            seen.add(evaluate_hand(cards[:2], cards[2:]).rank)

    assert seen == set(HandCategory)


@pytest.mark.parametrize(
    ("cards", "category", "tiebreaker"),
    [
        # A higher straight is preferred to the wheel.
        (["AS", "2D", "3C", "4H", "5S", "6D", "KC"], HandCategory.STRAIGHT, (6,)),
        (["AS", "2D", "3C", "4H", "5S", "9D", "KC"], HandCategory.STRAIGHT, (5,)),
        # Two sets of trips make a full house with the higher one.
        (["KS", "KD", "KC", "7H", "7S", "7D", "2C"], HandCategory.FULL_HOUSE, (13, 7)),
        # The kicker of quads can come from a pair.
        (
            ["9S", "9D", "9C", "9H", "QS", "QD", "2C"],
            HandCategory.FOUR_OF_A_KIND,
            (9, 12),
        ),
        # With three pairs, the third pair can be the kicker.
        (
            ["AS", "AD", "8C", "8H", "QS", "QD", "2C"],
            HandCategory.TWO_PAIR,
            (14, 12, 8),
        ),
        # A straight flush beats a higher flush in the same suit.
        (
            ["AH", "9H", "8H", "7H", "6H", "5H", "2C"],
            HandCategory.STRAIGHT_FLUSH,
            (9,),
        ),
    ],
)
def test_tricky_hands(
    cards: list[Card], category: HandCategory, tiebreaker: tuple[int, ...]
) -> None:
    evaluation = evaluate_hand(cards[:2], cards[2:])

    assert evaluation.rank == category
    assert evaluation.tiebreaker == tiebreaker
    assert_same_evaluation(cards)
