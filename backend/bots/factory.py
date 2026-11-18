"""Creation of bot controllers from their name."""

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from backend.application.controllers import PlayerController

from .basic_bot import BasicBot
from .profiles import (
    BASIC_PROFILE,
    CALLING_STATION_PROFILE,
    LAG_PROFILE,
    MANIAC_PROFILE,
    NIT_PROFILE,
    TAG_PROFILE,
    BotProfile,
)
from .random_bot import RandomBot
from .strategy_bot import StrategyBot

ProfileOverrides = Sequence[tuple[str, float]]
"""(parameter name, value) pairs replacing parameters of a profile."""


@dataclass(frozen=True)
class BotType:
    """A kind of bot that can be seated at a simulated table.

    ``profile`` is the play style of a heuristic bot. A bot without one
    (random, strategy bots) is built by ``build`` and has no parameters.
    """

    key: str
    label: str
    description: str
    profile: BotProfile | None
    build: Callable[[random.Random], PlayerController] = RandomBot

    def build_profile(self, overrides: ProfileOverrides = ()) -> BotProfile | None:
        """Return the profile with some parameters replaced."""
        if not overrides:
            return self.profile

        if self.profile is None:
            raise ValueError(f"The {self.label} bot has no parameters to change.")

        unknown = {name for name, _ in overrides} - set(BotProfile.parameter_names())

        if unknown:
            raise ValueError(
                f"Unknown profile parameters: {', '.join(sorted(unknown))}."
            )

        return replace(self.profile, **dict(overrides))

    def create(
        self, rng: random.Random, overrides: ProfileOverrides = ()
    ) -> PlayerController:
        profile = self.build_profile(overrides)

        if profile is None:
            return self.build(rng)

        return BasicBot(rng, profile=profile)


BOT_TYPES: dict[str, BotType] = {
    bot_type.key: bot_type
    for bot_type in (
        BotType(
            key="nit",
            label="Nit",
            description="Very tight and passive: waits for premium hands.",
            profile=NIT_PROFILE,
        ),
        BotType(
            key="tag",
            label="TAG",
            description="Tight-aggressive: few hands, played hard.",
            profile=TAG_PROFILE,
        ),
        BotType(
            key="lag",
            label="LAG",
            description="Loose-aggressive: many hands, lots of pressure.",
            profile=LAG_PROFILE,
        ),
        BotType(
            key="station",
            label="Calling Station",
            description="Loose-passive: calls almost anything, rarely raises.",
            profile=CALLING_STATION_PROFILE,
        ),
        BotType(
            key="maniac",
            label="Maniac",
            description="Very loose, very aggressive: bets and raises constantly.",
            profile=MANIAC_PROFILE,
        ),
        BotType(
            key="basic",
            label="Basic",
            description="Plays its hand strength against the pot odds.",
            profile=BASIC_PROFILE,
        ),
        BotType(
            key="shark",
            label="Shark",
            description=(
                "Plays by the numbers: position charts, opponents' ranges, "
                "Monte Carlo equity and expected value."
            ),
            profile=None,
            build=StrategyBot,
        ),
        BotType(
            key="adaptive",
            label="Adaptive",
            description=(
                "A Shark that learns each opponent's habits as it plays and "
                "exploits them."
            ),
            profile=None,
            build=lambda rng: StrategyBot(rng, adaptive=True),
        ),
        BotType(
            key="random",
            label="Random",
            description="Picks any legal action at random.",
            profile=None,
        ),
    )
}


def get_bot_type(key: str) -> BotType:
    """Return the bot type registered under ``key``."""
    try:
        return BOT_TYPES[key]
    except KeyError:
        known = ", ".join(BOT_TYPES)
        raise ValueError(f"Unknown bot {key!r}. Known bots: {known}.") from None


def create_bot(
    key: str, rng: random.Random, overrides: ProfileOverrides = ()
) -> PlayerController:
    """Create a bot of the given type, drawing its decisions from ``rng``."""
    return get_bot_type(key).create(rng, overrides)


# --- Random lineups (V3.1) ----------------------------------------------------


class Difficulty(StrEnum):
    """How strong a field of bots drawn at random is."""

    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


DIFFICULTY_LABELS = {
    Difficulty.EASY: "Easy — no Shark or Adaptive",
    Difficulty.NORMAL: "Normal — every style, a few strong bots",
    Difficulty.HARD: "Hard — mostly Sharks and Adaptives",
}
DIFFICULTY_WEIGHTS: dict[Difficulty, dict[str, int]] = {
    Difficulty.EASY: {
        "station": 3,
        "maniac": 2,
        "basic": 2,
        "nit": 2,
        "lag": 1,
        "tag": 1,
        "random": 1,
    },
    Difficulty.NORMAL: {
        "tag": 3,
        "lag": 2,
        "nit": 2,
        "station": 2,
        "basic": 2,
        "maniac": 1,
        "shark": 1,
        "adaptive": 1,
    },
    Difficulty.HARD: {
        "shark": 3,
        "adaptive": 3,
        "tag": 2,
        "lag": 2,
        "nit": 1,
        "basic": 1,
    },
}
"""Relative chance of each style being drawn, by difficulty."""


def random_styles(
    count: int, difficulty: Difficulty, rng: random.Random
) -> tuple[str, ...]:
    """The play styles of ``count`` bots drawn at random for ``difficulty``."""
    weights = DIFFICULTY_WEIGHTS[difficulty]

    return tuple(rng.choices(tuple(weights), weights=tuple(weights.values()), k=count))
