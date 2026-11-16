"""Play styles: presets, parameter overrides and measured tendencies."""

import random

import pytest

from backend.application.setup import BotLevel, create_bot
from backend.bots.basic_bot import BasicBot
from backend.bots.factory import BOT_TYPES, get_bot_type
from backend.bots.profiles import BASIC_PROFILE, BotProfile
from backend.bots.random_bot import RandomBot
from backend.simulation.config import SeatSpec, SimulationConfig
from backend.simulation.runner import run_simulation
from backend.simulation.stats import PlayerStats

STYLES = ("nit", "tag", "lag", "station", "maniac", "basic")


def test_the_default_profile_reproduces_the_original_basic_bot() -> None:
    # Recorded with the BasicBot of Alpha 2.0, before profiles existed.
    config = SimulationConfig(
        seats=(SeatSpec("basic"),) * 4 + (SeatSpec("random"),),
        hands=1500,
        batch_size=500,
        seed=20261116,
    )

    result = run_simulation(config)

    assert {
        name: (s.net_chips, s.net_chips_squared) for name, s in result.players.items()
    } == {
        "Basic": (19288, 75498700),
        "Basic 2": (17617, 68948087),
        "Basic 3": (6725, 80648671),
        "Basic 4": (31002, 91632510),
        "Random": (-74632, 167947546),
    }


def test_cash_game_bot_levels_keep_their_bots() -> None:
    rng = random.Random(0)

    normal = create_bot(BotLevel.NORMAL, rng)
    easy = create_bot(BotLevel.EASY, rng)

    assert isinstance(normal, BasicBot) and normal.profile == BASIC_PROFILE
    assert isinstance(easy, RandomBot)


def test_every_preset_has_a_label_and_a_description() -> None:
    assert set(STYLES) | {"random"} == set(BOT_TYPES)

    for bot_type in BOT_TYPES.values():
        assert bot_type.label
        assert bot_type.description.endswith(".")


def test_overrides_replace_profile_parameters() -> None:
    profile = get_bot_type("tag").build_profile((("bluff_probability", 0.3),))

    assert profile is not None
    assert profile.bluff_probability == 0.3
    assert profile.raise_threshold == get_bot_type("tag").profile.raise_threshold  # type: ignore[union-attr]


def test_unknown_or_impossible_overrides_are_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown profile parameters"):
        get_bot_type("tag").build_profile((("courage", 1.0),))

    with pytest.raises(ValueError, match="no parameters"):
        get_bot_type("random").build_profile((("bluff_probability", 0.1),))

    with pytest.raises(ValueError, match="between 0 and 1"):
        BotProfile(bluff_probability=1.5)


@pytest.fixture(scope="module")
def style_stats() -> dict[str, PlayerStats]:
    """Every style at one 6-max table, over a few thousand seeded hands."""
    config = SimulationConfig(
        seats=tuple(SeatSpec(style) for style in STYLES), hands=3000, seed=31
    )
    result = run_simulation(config)

    return {BOT_TYPES[stats.bot].key: stats for stats in result.players.values()}


def test_looser_styles_play_more_hands(style_stats: dict[str, PlayerStats]) -> None:
    vpip = {style: style_stats[style].vpip or 0.0 for style in STYLES}

    assert vpip["nit"] < vpip["tag"] < vpip["lag"] < vpip["maniac"]
    assert vpip["station"] > vpip["tag"]


def test_aggression_matches_the_styles(style_stats: dict[str, PlayerStats]) -> None:
    factors = {style: style_stats[style].aggression_factor or 0.0 for style in STYLES}

    assert min(factors, key=factors.__getitem__) == "station"
    assert max(factors, key=factors.__getitem__) == "maniac"
    assert style_stats["tag"].pfr > style_stats["nit"].pfr  # type: ignore[operator]
    assert style_stats["station"].pfr < style_stats["tag"].pfr  # type: ignore[operator]


def test_calling_station_rarely_folds_to_a_cbet(
    style_stats: dict[str, PlayerStats],
) -> None:
    assert (style_stats["station"].fold_to_cbet or 0.0) < (
        style_stats["nit"].fold_to_cbet or 1.0
    )
