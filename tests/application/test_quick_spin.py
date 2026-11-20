"""The Spin & Go started in one click, and the play style of every bot (V3.2)."""

import random

import pytest

from backend.application.controllers import HumanController
from backend.application.payouts import FAIR_MULTIPLIERS
from backend.application.setup import (
    DEFAULT_QUICK_SPIN_DIFFICULTY,
    LEVELS_BY_TIME,
    QUICK_SPIN_BUY_INS,
    QUICK_SPIN_CLOCK,
    create_spin_and_go,
    quick_spin_settings,
)
from backend.bots.factory import BOT_TYPES, DIFFICULTY_WEIGHTS, Difficulty, create_bot
from backend.poker_engine.constants import NO_LIMIT


def test_the_buy_ins_go_from_1_to_100k() -> None:
    assert QUICK_SPIN_BUY_INS == (
        1,
        2,
        5,
        10,
        20,
        25,
        50,
        100,
        500,
        1_000,
        2_000,
        2_500,
        5_000,
        10_000,
        25_000,
        50_000,
        100_000,
    )
    assert QUICK_SPIN_CLOCK == "Standard"
    assert DEFAULT_QUICK_SPIN_DIFFICULTY == Difficulty.EASY


def test_a_quick_spin_is_no_limit_by_time_with_the_fair_multipliers() -> None:
    settings = quick_spin_settings(25, Difficulty.EASY, "Alice", random.Random(1))

    assert settings.buy_in == 25
    assert settings.player_name == "Alice"
    assert settings.betting == NO_LIMIT
    assert settings.betting.cap is None
    assert settings.levels_by == LEVELS_BY_TIME
    assert settings.multipliers == FAIR_MULTIPLIERS
    assert len(settings.opponents) == 2


@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_the_two_bots_are_drawn_for_the_difficulty(difficulty: Difficulty) -> None:
    rng = random.Random(7)
    drawn = {
        style
        for _ in range(200)
        for style in quick_spin_settings(10, difficulty, "Hero", rng).opponents
    }

    assert drawn <= set(DIFFICULTY_WEIGHTS[difficulty])
    assert len(drawn) > 2  # Not always the same two bots.


def test_easy_never_draws_a_shark_or_an_adaptive() -> None:
    rng = random.Random(3)

    for _ in range(300):
        opponents = quick_spin_settings(1, Difficulty.EASY, "Hero", rng).opponents
        assert not {"shark", "adaptive"} & set(opponents)


def test_the_same_seed_draws_the_same_bots() -> None:
    first = quick_spin_settings(100, Difficulty.HARD, "Hero", random.Random(9))
    second = quick_spin_settings(100, Difficulty.HARD, "Hero", random.Random(9))

    assert first == second


def test_a_quick_spin_starts_with_levels_by_time() -> None:
    settings = quick_spin_settings(5, Difficulty.NORMAL, "Hero", random.Random(2))
    tournament = create_spin_and_go(settings, HumanController(), random.Random(2))

    assert tournament.clock is not None
    assert tournament.config.buy_in == 5


# --- The play style of every bot -----------------------------------------------


@pytest.mark.parametrize("key", list(BOT_TYPES))
def test_every_bot_knows_its_play_style(key: str) -> None:
    assert create_bot(key, random.Random(0)).style == key


def test_a_human_has_no_play_style() -> None:
    assert HumanController().style is None


def test_a_spin_seats_bots_of_the_drawn_styles() -> None:
    settings = quick_spin_settings(5, Difficulty.HARD, "Hero", random.Random(4))
    tournament = create_spin_and_go(settings, HumanController(), random.Random(4))
    styles = sorted(
        str(controller.style)
        for name, controller in tournament.controllers.items()
        if name != "Hero"
    )

    assert styles == sorted(settings.opponents)
