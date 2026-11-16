"""Payout structures, prize rounding and the Spin & Go multipliers."""

import random
from collections import Counter
from fractions import Fraction
from math import sqrt

import pytest

from backend.application.payouts import (
    FAIR_MULTIPLIERS,
    HIGH_MULTIPLIER,
    MULTIPLIER_TABLES,
    REALISTIC_MULTIPLIERS,
    TOP_THREE,
    TOP_TWO,
    WINNER_TAKES_ALL,
    Multiplier,
    MultiplierTable,
    PayoutStructure,
    default_payout,
    split_prizes,
)


def test_winner_takes_all() -> None:
    assert WINNER_TAKES_ALL.prizes(600, entrants=6) == [600, 0, 0, 0, 0, 0]


def test_rounding_remainders_go_to_the_higher_places() -> None:
    # 101 x 65% = 65.65 and 101 x 35% = 35.35: one unit is left for 1st.
    assert TOP_TWO.prizes(101, entrants=4) == [66, 35, 0, 0]
    # 408 x 50/30/20 = 204 / 122.4 / 81.6: one unit left for 1st.
    assert TOP_THREE.prizes(408, entrants=5) == [205, 122, 81, 0, 0]
    # 9 x 50/30/20 = 4.5 / 2.7 / 1.8: two units left, for 1st and 2nd.
    assert TOP_THREE.prizes(9, entrants=3) == [5, 3, 1]


@pytest.mark.parametrize("pool", [0, 1, 7, 99, 100, 101, 12_345])
@pytest.mark.parametrize("payout", [WINNER_TAKES_ALL, TOP_TWO, TOP_THREE])
def test_prizes_always_sum_to_the_prize_pool(
    pool: int, payout: PayoutStructure
) -> None:
    for entrants in range(1, 7):
        prizes = payout.prizes(pool, entrants)

        assert sum(prizes) == pool
        assert len(prizes) == entrants
        assert prizes == sorted(prizes, reverse=True)


def test_missing_paid_places_go_to_the_winner() -> None:
    # 50/30/20 with two entrants pays 70/30.
    assert TOP_THREE.prizes(100, entrants=2) == [70, 30]


def test_invalid_payout_structures_are_rejected() -> None:
    for percentages in [(), (60, 30), (40, 60), (100, 0)]:
        with pytest.raises(ValueError):
            PayoutStructure("Bad", percentages)


def test_default_payouts_by_number_of_players() -> None:
    assert [default_payout(n) for n in range(2, 7)] == [
        WINNER_TAKES_ALL,
        WINNER_TAKES_ALL,
        TOP_TWO,
        TOP_TWO,
        TOP_TWO,
    ]


def test_tied_places_split_their_prizes() -> None:
    assert split_prizes([80, 0], 2) == [40, 40]
    # The indivisible unit goes to the first player in the order given.
    assert split_prizes([81, 0], 2) == [41, 40]
    assert split_prizes([30, 20, 11], 3) == [21, 20, 20]


# --- Multipliers ---------------------------------------------------------


@pytest.mark.parametrize("table", MULTIPLIER_TABLES, ids=lambda t: t.name)
def test_multiplier_probabilities_sum_to_one(table: MultiplierTable) -> None:
    assert sum(table.probability(entry) for entry in table.entries) == 1


def test_the_fair_table_expects_exactly_three_buy_ins() -> None:
    assert FAIR_MULTIPLIERS.expected_value == 3


def test_the_realistic_table_keeps_about_seven_percent() -> None:
    assert REALISTIC_MULTIPLIERS.expected_value == Fraction(278, 100)
    rake = 1 - REALISTIC_MULTIPLIERS.expected_value / 3
    assert 0.07 < rake < 0.08


@pytest.mark.parametrize("table", MULTIPLIER_TABLES, ids=lambda t: t.name)
def test_high_multipliers_pay_three_places(table: MultiplierTable) -> None:
    for entry in table.entries:
        expected = HIGH_MULTIPLIER if entry.value >= 100 else WINNER_TAKES_ALL
        assert entry.payout == expected


def test_seeded_draws_follow_the_configured_distribution() -> None:
    draws = 200_000
    rng = random.Random(2026)
    counts = Counter(FAIR_MULTIPLIERS.draw(rng).value for _ in range(draws))

    for entry in FAIR_MULTIPLIERS.entries:
        probability = float(FAIR_MULTIPLIERS.probability(entry))
        expected = draws * probability
        deviation = sqrt(draws * probability * (1 - probability))

        # Within 4.5 standard deviations: a false alarm is about one in
        # 150,000 per entry.
        assert abs(counts[entry.value] - expected) < 4.5 * deviation


def test_draws_are_reproducible_from_the_seed() -> None:
    first = [FAIR_MULTIPLIERS.draw(random.Random(7)).value for _ in range(3)]
    again = [FAIR_MULTIPLIERS.draw(random.Random(7)).value for _ in range(3)]

    assert first == again


def test_invalid_multiplier_tables_are_rejected() -> None:
    with pytest.raises(ValueError):
        MultiplierTable("Empty", ())

    with pytest.raises(ValueError):
        MultiplierTable("Zero", (Multiplier(2, 0),))
