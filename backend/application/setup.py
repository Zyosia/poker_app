"""Creation of a game from the settings chosen by the user."""

import random
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from backend.bots.basic_bot import BasicBot
from backend.bots.factory import create_bot as create_bot_of_type
from backend.bots.factory import get_bot_type
from backend.bots.random_bot import RandomBot
from backend.poker_engine.constants import MAX_TABLE_SEATS
from backend.poker_engine.session import GameConfig, create_session

from .controllers import PlayerController
from .game import PokerGame
from .payouts import FAIR_MULTIPLIERS, MultiplierTable, PayoutStructure
from .structures import SPIN_PLAYERS, TOURNAMENT_STARTING_STACK, structure_by_name
from .tournament import (
    LevelClock,
    RebuyRules,
    SpinConfig,
    Tournament,
    TournamentConfig,
    create_spin,
)

BOT_NAMES = ("Alex", "Bella", "Carlos", "Dana", "Elio", "Fiona")
DEFAULT_PLAYER_NAME = "Hero"
MAX_PLAYER_NAME_LENGTH = 12

TOURNAMENT_BUY_INS = (100, 500, 1_000, 5_000, 10_000)
SPIN_BUY_INS = (100, 500, 1_000, 5_000)
"""Buy-in presets of the setup screens; custom amounts (0 for a freeroll) too."""
DEFAULT_TOURNAMENT_BUY_IN = 1_000
DEFAULT_SPIN_BUY_IN = 1_000


class BotLevel(StrEnum):
    EASY = "easy"
    NORMAL = "normal"


@dataclass(frozen=True)
class GameSettings:
    """Choices made by the user before starting a game."""

    player_name: str = DEFAULT_PLAYER_NAME
    opponent_count: int = 3
    bot_level: BotLevel = BotLevel.NORMAL
    starting_stack: int = 1000
    small_blind: int = 5
    big_blind: int = 10

    def __post_init__(self) -> None:
        check_player_name(self.player_name)

        if not 1 <= self.opponent_count <= MAX_TABLE_SEATS - 1:
            raise ValueError(
                f"The number of opponents must be 1 to {MAX_TABLE_SEATS - 1}."
            )


def create_bot(level: BotLevel, rng: random.Random) -> PlayerController:
    """Create a bot of the given level with its own random generator."""
    bot_rng = random.Random(rng.random())

    if level == BotLevel.EASY:
        return RandomBot(bot_rng)

    return BasicBot(bot_rng)


def create_game(
    settings: GameSettings,
    human_controller: PlayerController,
    save_path: Path | None = None,
    rng: random.Random | None = None,
) -> PokerGame:
    """Create a game opposing one human player to bots.

    The human takes the first seat and the first dealer is drawn at random.
    """
    rng = rng or random.Random()

    bot_names = [name for name in BOT_NAMES if name != settings.player_name]
    bot_names = bot_names[: settings.opponent_count]

    session = create_session(
        player_names=[settings.player_name, *bot_names],
        config=GameConfig(
            starting_stack=settings.starting_stack,
            rebuy_stack=settings.starting_stack,
            small_blind=settings.small_blind,
            big_blind=settings.big_blind,
        ),
    )
    session.table.dealer_index = rng.randrange(len(session.players))

    controllers: dict[str, PlayerController] = {
        name: create_bot(settings.bot_level, rng) for name in bot_names
    }
    controllers[settings.player_name] = human_controller

    return PokerGame(session=session, controllers=controllers, save_path=save_path)


# --- Tournaments ---------------------------------------------------------------

LEVELS_BY_HANDS = "hands"
LEVELS_BY_TIME = "time"


@dataclass(frozen=True)
class TournamentSettings:
    """Choices made before a tournament: you against 1 to 5 bots.

    ``opponents`` lists the play style key of every bot (see
    ``backend.bots.factory``). Levels go up by hands or by playing time.
    """

    player_name: str = DEFAULT_PLAYER_NAME
    opponents: tuple[str, ...] = ("tag", "lag", "station", "maniac", "nit")
    starting_stack: int = TOURNAMENT_STARTING_STACK
    structure: str = "Turbo"
    levels_by: str = LEVELS_BY_HANDS
    buy_in: int = DEFAULT_TOURNAMENT_BUY_IN
    payout: PayoutStructure | None = None
    rebuys: bool = False

    def __post_init__(self) -> None:
        check_player_name(self.player_name)

        if not 1 <= len(self.opponents) <= MAX_TABLE_SEATS - 1:
            raise ValueError(
                f"The number of opponents must be 1 to {MAX_TABLE_SEATS - 1}."
            )

        if self.levels_by not in (LEVELS_BY_HANDS, LEVELS_BY_TIME):
            raise ValueError("Levels go up by hands or by time.")

        if self.starting_stack <= 0 or self.buy_in < 0:
            raise ValueError("Invalid starting stack or buy-in.")

        for bot in self.opponents:
            get_bot_type(bot)

        structure_by_name(self.structure)

    def tournament_config(self) -> TournamentConfig:
        rebuys = None

        if self.rebuys:
            rebuys = RebuyRules(
                levels=3,
                threshold=self.starting_stack,
                rebuy_stack=self.starting_stack,
                add_on_stack=self.starting_stack,
            )

        return TournamentConfig(
            structure=structure_by_name(self.structure),
            starting_stack=self.starting_stack,
            buy_in=self.buy_in,
            payout=self.payout,
            rebuys=rebuys,
        )


@dataclass(frozen=True)
class SpinSettings:
    """Choices made before a Spin & Go: you against two bots."""

    player_name: str = DEFAULT_PLAYER_NAME
    opponents: tuple[str, str] = ("tag", "lag")
    buy_in: int = DEFAULT_SPIN_BUY_IN
    levels_by: str = LEVELS_BY_HANDS
    multipliers: MultiplierTable = FAIR_MULTIPLIERS

    def __post_init__(self) -> None:
        check_player_name(self.player_name)

        if len(self.opponents) != SPIN_PLAYERS - 1:
            raise ValueError(f"A Spin & Go has {SPIN_PLAYERS - 1} opponents.")

        if self.levels_by not in (LEVELS_BY_HANDS, LEVELS_BY_TIME):
            raise ValueError("Levels go up by hands or by time.")

        if self.buy_in < 0:
            raise ValueError("The buy-in cannot be negative.")

        for bot in self.opponents:
            get_bot_type(bot)


def check_player_name(name: str) -> None:
    """The human's name: not empty, at most ``MAX_PLAYER_NAME_LENGTH`` long."""
    if not name.strip():
        raise ValueError("The player name cannot be empty.")

    if len(name) > MAX_PLAYER_NAME_LENGTH:
        raise ValueError(
            f"The player name is at most {MAX_PLAYER_NAME_LENGTH} characters long."
        )


def _seat_bots(
    player_name: str, opponents: tuple[str, ...], rng: random.Random
) -> tuple[list[str], dict[str, PlayerController]]:
    """Name the bots, each with its own random generator."""
    names = [name for name in BOT_NAMES if name != player_name][: len(opponents)]
    controllers = {
        name: create_bot_of_type(bot, random.Random(rng.getrandbits(64)))
        for name, bot in zip(names, opponents, strict=True)
    }

    return names, controllers


def create_tournament(
    settings: TournamentSettings,
    human_controller: PlayerController,
    rng: random.Random | None = None,
    clock_source: Callable[[], float] | None = None,
) -> Tournament:
    """A tournament opposing the human (first seat) to bots.

    The hands are kept for the history and the save file. Levels by time
    use a ``LevelClock`` on ``clock_source`` (``time.monotonic`` by default).
    """
    rng = rng or random.Random()
    bot_names, controllers = _seat_bots(settings.player_name, settings.opponents, rng)
    controllers[settings.player_name] = human_controller
    seats = [settings.player_name, *bot_names]

    return Tournament(
        settings.tournament_config(),
        seats,
        controllers,
        dealer_index=rng.randrange(len(seats)),
        deck_rng=random.Random(rng.getrandbits(64)),
        clock=_clock(settings.levels_by, clock_source),
        keep_hands=True,
    )


def create_spin_and_go(
    settings: SpinSettings,
    human_controller: PlayerController,
    rng: random.Random | None = None,
    clock_source: Callable[[], float] | None = None,
) -> Tournament:
    """A Spin & Go: the multiplier is drawn first, then the hands are dealt."""
    rng = rng or random.Random()
    bot_names, controllers = _seat_bots(settings.player_name, settings.opponents, rng)
    controllers[settings.player_name] = human_controller

    return create_spin(
        SpinConfig(multipliers=settings.multipliers, buy_in=settings.buy_in),
        [settings.player_name, *bot_names],
        controllers,
        random.Random(rng.getrandbits(64)),
        clock=_clock(settings.levels_by, clock_source),
        keep_hands=True,
    )


def _clock(
    levels_by: str, clock_source: Callable[[], float] | None
) -> LevelClock | None:
    if levels_by != LEVELS_BY_TIME:
        return None

    return LevelClock(clock_source) if clock_source else LevelClock()
