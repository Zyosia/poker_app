"""Validation of the simulation configuration."""

from typing import Any

import pytest

from backend.simulation.config import (
    SeatSpec,
    SimulationConfig,
    StackPolicy,
    derive_seed,
)


def seats(*bots: str) -> tuple[SeatSpec, ...]:
    return tuple(SeatSpec(bot) for bot in bots)


def test_seat_names_default_to_the_bot_label_and_are_numbered_when_repeated() -> None:
    config = SimulationConfig(
        seats=(*seats("basic", "random", "basic"), SeatSpec("random", name="Rob"))
    )

    assert config.seat_names == ("Basic", "Random", "Basic 2", "Rob")


def test_duplicate_seat_names_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        SimulationConfig(
            seats=(SeatSpec("basic", name="Bot"), SeatSpec("random", name="Bot"))
        )


@pytest.mark.parametrize("seat_count", [1, 10])
def test_a_table_needs_two_to_nine_seats(seat_count: int) -> None:
    with pytest.raises(ValueError, match="2 to 9 seats"):
        SimulationConfig(seats=seats(*["basic"] * seat_count))


def test_an_unknown_bot_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown bot"):
        SeatSpec("genius")


@pytest.mark.parametrize(
    "field_name",
    ["hands", "sessions", "workers", "batch_size", "starting_stack", "small_blind"],
)
def test_counts_and_amounts_must_be_positive(field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        options: dict[str, Any] = {field_name: 0}
        SimulationConfig(seats=seats("basic", "basic"), **options)


def test_the_big_blind_must_exceed_the_small_blind() -> None:
    with pytest.raises(ValueError, match="big blind"):
        SimulationConfig(seats=seats("basic", "basic"), small_blind=10, big_blind=10)


@pytest.mark.parametrize("policy", [StackPolicy.AUTO_REBUY, StackPolicy.ELIMINATION])
def test_duplicate_mode_requires_the_reset_policy(policy: StackPolicy) -> None:
    with pytest.raises(ValueError, match="Duplicate mode"):
        SimulationConfig(
            seats=seats("basic", "basic"), stack_policy=policy, duplicate=True
        )


def test_duplicate_deals_cover_the_hand_budget() -> None:
    config = SimulationConfig(
        seats=seats("basic", "basic", "random"), hands=100, duplicate=True
    )

    assert config.deals == 34


def test_with_seed_keeps_an_existing_seed_and_draws_one_otherwise() -> None:
    seeded = SimulationConfig(seats=seats("basic", "basic"), seed=42)
    unseeded = SimulationConfig(seats=seats("basic", "basic"))

    assert seeded.with_seed() is seeded
    assert unseeded.with_seed().seed is not None


def test_derived_seeds_are_stable_and_distinct() -> None:
    # A pinned value: the derivation must never depend on the process or run.
    assert derive_seed(1, "batch", 0) == 18112433553247380577
    assert derive_seed(1, "batch", 0) != derive_seed(1, "batch", 1)
    assert derive_seed(1, "batch", 0) != derive_seed(2, "batch", 0)
