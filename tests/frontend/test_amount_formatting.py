"""Amounts shown in chips or in big blinds, and amounts typed in big blinds."""

import pytest

from frontend.formatting import (
    big_blinds_to_chips,
    format_amount,
    format_big_blinds,
    format_chips,
)


def test_chips_are_grouped_by_thousands() -> None:
    assert format_chips(0) == "0"
    assert format_chips(950) == "950"
    assert format_chips(12500) == "12 500"
    assert format_chips(1_250_000) == "1 250 000"


@pytest.mark.parametrize(
    ("chips", "big_blind", "expected"),
    [
        (400, 20, "20 BB"),  # Whole number: no trailing ".0".
        (850, 20, "42.5 BB"),
        (0, 20, "0 BB"),
        (10, 20, "0.5 BB"),
        (1, 20, "0.1 BB"),  # 0.05 rounds half up.
        (1, 30, "0 BB"),  # 0.033 rounds down.
        (1000, 30, "33.3 BB"),  # The big blind does not divide the amount.
        (1001, 30, "33.4 BB"),  # 33.366… rounds up.
        (1990, 200, "10 BB"),  # 9.95 rounds up to a whole number.
        (12_345_600, 100, "123 456 BB"),  # Huge stack, grouped.
        (12_345_650, 100, "123 456.5 BB"),
        (-850, 20, "-42.5 BB"),
    ],
)
def test_big_blinds_have_one_decimal_at_most(
    chips: int, big_blind: int, expected: str
) -> None:
    assert format_big_blinds(chips, big_blind) == expected


def test_format_amount_follows_the_unit() -> None:
    assert format_amount(12500) == "12 500"
    assert format_amount(12500, big_blind=100) == "125 BB"


def test_the_big_blind_must_be_positive() -> None:
    with pytest.raises(ValueError):
        format_big_blinds(100, 0)


@pytest.mark.parametrize(
    ("big_blinds", "big_blind", "expected"),
    [
        (4, 20, 80),
        (4.5, 20, 90),
        (2.3, 30, 69),
        (2.25, 30, 68),  # 67.5 rounds half up to the nearest chip.
        (0.1, 5, 1),  # 0.5 chip rounds up.
    ],
)
def test_big_blinds_convert_to_the_nearest_chip(
    big_blinds: float, big_blind: int, expected: int
) -> None:
    assert big_blinds_to_chips(big_blinds, big_blind, 0, 10_000) == expected


def test_converted_amounts_stay_within_the_legal_range() -> None:
    # Raise to between 45 and 517 chips, with a big blind of 20.
    assert big_blinds_to_chips(2, 20, 45, 517) == 45  # 40 is below the minimum.
    assert big_blinds_to_chips(2.3, 20, 45, 517) == 46
    assert big_blinds_to_chips(25.9, 20, 45, 517) == 517  # 518 is above the max.
    assert big_blinds_to_chips(1000, 20, 45, 517) == 517

    with pytest.raises(ValueError):
        big_blinds_to_chips(3, 20, 100, 50)
