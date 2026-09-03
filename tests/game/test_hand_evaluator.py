from dataclasses import FrozenInstanceError

import pytest

from backend.game.hand_evaluator import (
    CATEGORY_FLUSH,
    CATEGORY_FOUR_OF_A_KIND,
    CATEGORY_FULL_HOUSE,
    CATEGORY_HIGH_CARD,
    CATEGORY_PAIR,
    CATEGORY_STRAIGHT,
    CATEGORY_STRAIGHT_FLUSH,
    CATEGORY_THREE_OF_A_KIND,
    CATEGORY_TWO_PAIR,
    card_rank,
    card_suit,
    evaluate_five_cards,
    evaluate_hand,
    get_straight_high,
)

# ============================================================
# Helpers
# ============================================================


def cards(*cards: str) -> list[str]:
    """Make card lists easier to read in tests."""
    return list(cards)


# ============================================================
# Five-card hand categories
# ============================================================


def test_high_card() -> None:
    evaluation = evaluate_five_cards(
        cards("AS", "KD", "9C", "7H", "3S"),
    )
    assert evaluation.rank == CATEGORY_HIGH_CARD
    assert evaluation.name == "High Card"
    assert evaluation.tiebreaker == (14, 13, 9, 7, 3)


def test_pair() -> None:
    evaluation = evaluate_five_cards(
        cards("AS", "AD", "9C", "7H", "3S"),
    )
    assert evaluation.rank == CATEGORY_PAIR
    assert evaluation.name == "Pair"
    assert evaluation.tiebreaker == (14, 9, 7, 3)


def test_two_pair() -> None:
    evaluation = evaluate_five_cards(
        cards("AS", "AD", "9C", "9H", "3S"),
    )
    assert evaluation.rank == CATEGORY_TWO_PAIR
    assert evaluation.name == "Two Pair"
    assert evaluation.tiebreaker == (14, 9, 3)


def test_three_of_a_kind() -> None:
    evaluation = evaluate_five_cards(
        cards("AS", "AD", "AC", "9H", "3S"),
    )
    assert evaluation.rank == CATEGORY_THREE_OF_A_KIND
    assert evaluation.name == "Three of a Kind"
    assert evaluation.tiebreaker == (14, 9, 3)


def test_straight() -> None:
    evaluation = evaluate_five_cards(
        cards("AS", "KD", "QC", "JH", "TS"),
    )
    assert evaluation.rank == CATEGORY_STRAIGHT
    assert evaluation.name == "Straight"
    assert evaluation.tiebreaker == (14,)


def test_flush() -> None:
    evaluation = evaluate_five_cards(
        cards("AS", "JS", "9S", "7S", "3S"),
    )
    assert evaluation.rank == CATEGORY_FLUSH
    assert evaluation.name == "Flush"
    assert evaluation.tiebreaker == (14, 11, 9, 7, 3)


def test_full_house() -> None:
    evaluation = evaluate_five_cards(
        cards("AS", "AD", "AC", "9H", "9S"),
    )

    assert evaluation.rank == CATEGORY_FULL_HOUSE
    assert evaluation.name == "Full House"
    assert evaluation.tiebreaker == (14, 9)


def test_four_of_a_kind() -> None:
    evaluation = evaluate_five_cards(
        cards("AS", "AD", "AC", "AH", "9S"),
    )

    assert evaluation.rank == CATEGORY_FOUR_OF_A_KIND
    assert evaluation.name == "Four of a Kind"
    assert evaluation.tiebreaker == (14, 9)


def test_straight_flush() -> None:
    evaluation = evaluate_five_cards(
        cards("AS", "KS", "QS", "JS", "TS"),
    )

    assert evaluation.rank == CATEGORY_STRAIGHT_FLUSH
    assert evaluation.name == "Straight Flush"
    assert evaluation.tiebreaker == (14,)


# ============================================================
# Ace-low straight
# ============================================================


def test_ace_low_straight() -> None:
    evaluation = evaluate_five_cards(
        cards("AS", "2D", "3C", "4H", "5S"),
    )

    assert evaluation.rank == CATEGORY_STRAIGHT
    assert evaluation.tiebreaker == (5,)


def test_ace_low_straight_flush() -> None:
    evaluation = evaluate_five_cards(
        cards("AS", "2S", "3S", "4S", "5S"),
    )

    assert evaluation.rank == CATEGORY_STRAIGHT_FLUSH
    assert evaluation.tiebreaker == (5,)


# ============================================================
# Tiebreakers
# ============================================================


def test_higher_pair_wins() -> None:
    ace_pair = evaluate_five_cards(
        cards("AS", "AD", "KC", "7H", "3S"),
    )

    king_pair = evaluate_five_cards(
        cards("KS", "KD", "QC", "7H", "3S"),
    )

    assert ace_pair.comparison_key() > king_pair.comparison_key()


def test_same_pair_higher_kicker_wins() -> None:
    ace_kicker = evaluate_five_cards(
        cards("AS", "AD", "KC", "7H", "3S"),
    )

    king_kicker = evaluate_five_cards(
        cards("AS", "AD", "QC", "7H", "3S"),
    )

    assert ace_kicker.comparison_key() > king_kicker.comparison_key()


def test_two_pair_high_pair_matters_first() -> None:
    aces_and_kings = evaluate_five_cards(
        cards("AS", "AD", "KC", "KH", "3S"),
    )

    kings_and_queens = evaluate_five_cards(
        cards("KS", "KD", "QC", "QH", "3S"),
    )

    assert aces_and_kings.comparison_key() > kings_and_queens.comparison_key()


def test_two_pair_low_pair_matters_second() -> None:
    aces_and_kings = evaluate_five_cards(
        cards("AS", "AD", "KC", "KH", "3S"),
    )

    aces_and_queens = evaluate_five_cards(
        cards("AS", "AD", "QC", "QH", "3S"),
    )

    assert aces_and_kings.comparison_key() > aces_and_queens.comparison_key()


def test_two_pair_kicker_matters_last() -> None:
    first = evaluate_five_cards(
        cards("AS", "AD", "KC", "KH", "9S"),
    )

    second = evaluate_five_cards(
        cards("AS", "AD", "KC", "KH", "8S"),
    )

    assert first.comparison_key() > second.comparison_key()


def test_three_of_a_kind_kicker_comparison() -> None:
    first = evaluate_five_cards(
        cards("AS", "AD", "AC", "KH", "9S"),
    )

    second = evaluate_five_cards(
        cards("AS", "AD", "AC", "QH", "9S"),
    )

    assert first.comparison_key() > second.comparison_key()


def test_full_house_trips_are_compared_first() -> None:
    aces_full = evaluate_five_cards(
        cards("AS", "AD", "AC", "KH", "KS"),
    )

    kings_full = evaluate_five_cards(
        cards("KS", "KD", "KC", "AH", "AS"),
    )

    assert aces_full.comparison_key() > kings_full.comparison_key()


def test_full_house_pair_is_used_as_tiebreaker() -> None:
    higher_pair = evaluate_five_cards(
        cards("AS", "AD", "AC", "KH", "KS"),
    )

    lower_pair = evaluate_five_cards(
        cards("AS", "AD", "AC", "QH", "QS"),
    )

    assert higher_pair.comparison_key() > lower_pair.comparison_key()


def test_four_of_a_kind_kicker_comparison() -> None:
    first = evaluate_five_cards(
        cards("AS", "AD", "AC", "AH", "KS"),
    )

    second = evaluate_five_cards(
        cards("AS", "AD", "AC", "AH", "QS"),
    )

    assert first.comparison_key() > second.comparison_key()


def test_flush_uses_all_five_cards_for_tiebreaking() -> None:
    first = evaluate_five_cards(
        cards("AS", "JS", "9S", "7S", "3S"),
    )

    second = evaluate_five_cards(
        cards("AS", "TS", "9S", "7S", "3S"),
    )

    assert first.comparison_key() > second.comparison_key()


def test_straight_compares_high_card_only() -> None:
    ace_high = evaluate_five_cards(
        cards("AS", "KD", "QC", "JH", "TS"),
    )

    king_high = evaluate_five_cards(
        cards("KS", "QD", "JC", "TH", "9S"),
    )

    assert ace_high.comparison_key() > king_high.comparison_key()


# ============================================================
# Category ordering
# ============================================================


def test_category_ordering() -> None:
    hands = [
        evaluate_five_cards(
            cards("AS", "KD", "9C", "7H", "3S"),
        ),
        evaluate_five_cards(
            cards("AS", "AD", "9C", "7H", "3S"),
        ),
        evaluate_five_cards(
            cards("AS", "AD", "9C", "9H", "3S"),
        ),
        evaluate_five_cards(
            cards("AS", "AD", "AC", "9H", "3S"),
        ),
        evaluate_five_cards(
            cards("AS", "KD", "QC", "JH", "TS"),
        ),
        evaluate_five_cards(
            cards("AS", "JS", "9S", "7S", "3S"),
        ),
        evaluate_five_cards(
            cards("AS", "AD", "AC", "9H", "9S"),
        ),
        evaluate_five_cards(
            cards("AS", "AD", "AC", "AH", "9S"),
        ),
        evaluate_five_cards(
            cards("AS", "KS", "QS", "JS", "TS"),
        ),
    ]

    ranks = [evaluation.rank for evaluation in hands]

    assert ranks == list(range(9))


# ============================================================
# Best five cards from Hold'em's seven cards
# ============================================================


def test_evaluate_hand_uses_best_five_of_seven() -> None:
    evaluation = evaluate_hand(
        hole_cards=cards("AS", "AD"),
        community_cards=cards(
            "AC",
            "AH",
            "KS",
            "2D",
        ),
    )

    assert evaluation.rank == CATEGORY_FOUR_OF_A_KIND
    assert evaluation.tiebreaker == (14, 13)


def test_evaluate_hand_can_use_only_community_cards() -> None:
    evaluation = evaluate_hand(
        hole_cards=cards("2C", "3D"),
        community_cards=cards(
            "AS",
            "KS",
            "QS",
            "JS",
            "TS",
        ),
    )

    assert evaluation.rank == CATEGORY_STRAIGHT_FLUSH
    assert evaluation.tiebreaker == (14,)


def test_evaluate_hand_can_use_both_hole_cards() -> None:
    evaluation = evaluate_hand(
        hole_cards=cards("AS", "KS"),
        community_cards=cards(
            "QS",
            "JS",
            "TS",
            "2D",
            "3C",
        ),
    )

    assert evaluation.rank == CATEGORY_STRAIGHT_FLUSH
    assert evaluation.tiebreaker == (14,)


def test_evaluate_hand_can_use_neither_hole_card() -> None:
    evaluation = evaluate_hand(
        hole_cards=cards("2C", "3D"),
        community_cards=cards(
            "AS",
            "KS",
            "QS",
            "JS",
            "TS",
        ),
    )

    assert evaluation.cards == (
        "AS",
        "KS",
        "QS",
        "JS",
        "TS",
    )


# ============================================================
# Comparison equality
# ============================================================


def test_identical_evaluations_have_same_comparison_key() -> None:
    first = evaluate_five_cards(
        cards("AS", "KD", "QC", "JH", "9S"),
    )

    second = evaluate_five_cards(
        cards("AH", "KC", "QD", "JS", "9H"),
    )

    assert first.comparison_key() == second.comparison_key()


# ============================================================
# Card parsing
# ============================================================


def test_card_rank() -> None:
    assert card_rank("2C") == 2
    assert card_rank("9D") == 9
    assert card_rank("TS") == 10
    assert card_rank("AS") == 14


def test_card_suit() -> None:
    assert card_suit("2C") == "C"
    assert card_suit("9D") == "D"
    assert card_suit("TS") == "S"
    assert card_suit("AH") == "H"


def test_invalid_card_length_for_rank() -> None:

    with pytest.raises(ValueError):
        card_rank("A")


def test_invalid_card_length_for_suit() -> None:

    with pytest.raises(ValueError):
        card_suit("A")


def test_invalid_card_rank() -> None:

    with pytest.raises(ValueError):
        card_rank("XC")


def test_invalid_card_rank_with_invalid_length() -> None:

    with pytest.raises(ValueError):
        card_rank("ABC")


# ============================================================
# Straight detection
# ============================================================


def test_get_straight_high_returns_highest_card() -> None:
    assert (
        get_straight_high(
            [14, 13, 12, 11, 10],
        )
        == 14
    )


def test_get_straight_high_detects_middle_straight() -> None:
    assert (
        get_straight_high(
            [9, 8, 7, 6, 5],
        )
        == 9
    )


def test_get_straight_high_detects_ace_low() -> None:
    assert (
        get_straight_high(
            [14, 5, 4, 3, 2],
        )
        == 5
    )


def test_get_straight_high_returns_none_when_no_straight() -> None:
    assert (
        get_straight_high(
            [14, 13, 11, 8, 2],
        )
        is None
    )


def test_get_straight_high_ignores_duplicate_ranks() -> None:
    assert (
        get_straight_high(
            [14, 13, 12, 11, 10, 10],
        )
        == 14
    )


# ============================================================
# Invalid input
# ============================================================


def test_evaluate_five_cards_requires_exactly_five_cards() -> None:

    with pytest.raises(ValueError):
        evaluate_five_cards(
            cards("AS", "KD", "QC", "JH"),
        )


def test_evaluate_five_cards_rejects_more_than_five_cards() -> None:

    with pytest.raises(ValueError):
        evaluate_five_cards(
            cards(
                "AS",
                "KD",
                "QC",
                "JH",
                "TS",
                "9C",
            ),
        )


def test_evaluate_hand_requires_at_least_five_cards() -> None:

    with pytest.raises(ValueError):
        evaluate_hand(
            hole_cards=cards("AS", "KD"),
            community_cards=cards(
                "QC",
                "JH",
            ),
        )


def test_evaluate_hand_rejects_more_than_seven_cards() -> None:

    with pytest.raises(ValueError):
        evaluate_hand(
            hole_cards=cards("AS", "KD", "QC"),
            community_cards=cards(
                "JH",
                "TS",
                "9C",
                "8D",
                "7H",
            ),
        )


# ============================================================
# Dataclass behaviour
# ============================================================


def test_hand_evaluation_is_immutable() -> None:
    evaluation = evaluate_five_cards(
        cards("AS", "KD", "QC", "JH", "9S"),
    )

    with pytest.raises(FrozenInstanceError):
        evaluation.rank = 42  # type: ignore[misc]
