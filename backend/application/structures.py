"""The default tournament blind structures, in one place.

Every structure posts a big-blind ante (equal to the big blind) from level 4.
``with_classic_antes`` turns it into classic antes (a tenth of the big blind,
posted by every player).

Turbo, Regular and Deep share their levels and differ by their pace: hands
per level in simulations, minutes per level when you play.
"""

from dataclasses import replace

from backend.poker_engine.blinds import AnteType, BlindLevel, BlindStructure

ANTES_FROM_LEVEL = 4

TOURNAMENT_STARTING_STACK = 1500


def _levels(blinds: tuple[tuple[int, int], ...]) -> tuple[BlindLevel, ...]:
    return tuple(
        BlindLevel(
            small_blind=small,
            big_blind=big,
            ante=big if number >= ANTES_FROM_LEVEL else 0,
            ante_type=AnteType.BIG_BLIND,
        )
        for number, (small, big) in enumerate(blinds, start=1)
    )


TOURNAMENT_LEVELS = _levels(
    (
        (10, 20),
        (15, 30),
        (25, 50),
        (50, 100),
        (75, 150),
        (100, 200),
        (150, 300),
        (200, 400),
        (300, 600),
        (400, 800),
        (500, 1000),
        (750, 1500),
        (1000, 2000),
    )
)

TURBO = BlindStructure(
    "Turbo", TOURNAMENT_LEVELS, hands_per_level=6, minutes_per_level=3
)
REGULAR = BlindStructure(
    "Regular", TOURNAMENT_LEVELS, hands_per_level=10, minutes_per_level=6
)
DEEP = BlindStructure(
    "Deep", TOURNAMENT_LEVELS, hands_per_level=15, minutes_per_level=10
)

TOURNAMENT_STRUCTURES: tuple[BlindStructure, ...] = (TURBO, REGULAR, DEEP)

# --- Spin & Go --------------------------------------------------------------

SPIN_PLAYERS = 3
SPIN_STARTING_STACK = 500
"""25 big blinds at the first level."""

SPIN_HYPER_TURBO = BlindStructure(
    "Hyper-turbo",
    _levels(
        (
            (10, 20),
            (15, 30),
            (20, 40),
            (25, 50),
            (30, 60),
            (40, 80),
            (50, 100),
            (60, 120),
            (80, 160),
            (100, 200),
            (150, 300),
            (200, 400),
        )
    ),
    hands_per_level=5,
    minutes_per_level=2,
)


def with_classic_antes(structure: BlindStructure) -> BlindStructure:
    """The same structure with classic antes of a tenth of the big blind."""
    return replace(
        structure,
        levels=tuple(
            replace(
                level,
                ante=max(1, level.big_blind // 10) if level.ante else 0,
                ante_type=AnteType.CLASSIC,
            )
            for level in structure.levels
        ),
    )


def structure_by_name(name: str) -> BlindStructure:
    for structure in (*TOURNAMENT_STRUCTURES, SPIN_HYPER_TURBO):
        if structure.name.lower() == name.lower():
            return structure

    known = ", ".join(s.name for s in (*TOURNAMENT_STRUCTURES, SPIN_HYPER_TURBO))
    raise ValueError(f"Unknown blind structure {name!r}. Known: {known}.")
