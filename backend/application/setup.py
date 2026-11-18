"""Creation of a game from the settings chosen by the user."""

import random
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path

from backend.bots.factory import create_bot, get_bot_type
from backend.poker_engine.constants import MAX_TABLE_SEATS
from backend.poker_engine.session import GameConfig, create_session

from .controllers import PlayerController
from .game import PokerGame
from .payouts import FAIR_MULTIPLIERS, MultiplierTable, PayoutStructure
from .structures import SPIN_PLAYERS, TOURNAMENT_STARTING_STACK, structure_by_name
from .tournament import (
    MAX_ENTRANTS,
    LevelClock,
    RebuyRules,
    SpinConfig,
    Tournament,
    TournamentConfig,
    create_spin,
)

BOT_NAMES = (
    "Alex",
    "Bella",
    "Carlos",
    "Dana",
    "Elio",
    "Fiona",
    "Gus",
    "Hana",
    "Ivo",
)
"""One more than a full table needs: a bot never takes the human's name."""
MORE_BOT_NAMES = (
    "Jade",
    "Kai",
    "Lena",
    "Milo",
    "Nora",
    "Oscar",
    "Paula",
    "Quinn",
    "Rosa",
    "Sami",
    "Tara",
    "Ugo",
    "Vera",
    "Wes",
    "Xena",
    "Yann",
    "Zoe",
    "Ana",
    "Boris",
    "Chloe",
    "Dario",
    "Emma",
    "Felix",
    "Greta",
    "Hugo",
    "Iris",
    "Jonas",
    "Kira",
    "Leo",
    "Maya",
    "Nico",
    "Olga",
    "Pablo",
    "Rita",
    "Sven",
    "Tess",
    "Umar",
    "Vic",
    "Wanda",
    "Yuri",
)
"""Names for the bots of a large tournament field, after ``BOT_NAMES``."""
DEFAULT_PLAYER_NAME = "Hero"
MAX_PLAYER_NAME_LENGTH = 12
MAX_BOT_NAME_LENGTH = 16

TOURNAMENT_BUY_INS = (100, 500, 1_000, 5_000, 10_000)
SPIN_BUY_INS = (100, 500, 1_000, 5_000)
"""Buy-in presets of the setup screens; custom amounts (0 for a freeroll) too."""
DEFAULT_TOURNAMENT_BUY_IN = 1_000
DEFAULT_SPIN_BUY_IN = 1_000


@dataclass(frozen=True)
class GameSettings:
    """Choices made by the user before starting a cash game.

    ``opponents`` lists the play style key of every bot (see
    ``backend.bots.factory``): 1 to 8 bots, up to a full-ring table.
    """

    player_name: str = DEFAULT_PLAYER_NAME
    opponents: tuple[str, ...] = ("tag", "lag", "station")
    starting_stack: int = 1000
    small_blind: int = 5
    big_blind: int = 10
    straddle: bool = False
    """The player under the gun straddles (two big blinds) every hand."""
    bots_rebuy: bool = True
    """Busted bots rebuy and short bots top up: the table stays full."""
    auto_top_up: bool = False
    """Your stack goes back to the maximum buy-in before every hand."""

    def __post_init__(self) -> None:
        check_player_name(self.player_name)
        check_opponents(self.opponents)


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
    names, controllers = _seat_bots(settings.player_name, settings.opponents, rng)

    session = create_session(
        player_names=[settings.player_name, *names],
        config=GameConfig(
            starting_stack=settings.starting_stack,
            rebuy_stack=settings.starting_stack,
            small_blind=settings.small_blind,
            big_blind=settings.big_blind,
            straddle=settings.straddle,
        ),
    )
    session.table.dealer_index = rng.randrange(len(session.players))
    controllers[settings.player_name] = human_controller

    return PokerGame(
        session=session,
        controllers=controllers,
        save_path=save_path,
        bots_rebuy=settings.bots_rebuy,
    )


# --- Tournaments ---------------------------------------------------------------

LEVELS_BY_HANDS = "hands"
LEVELS_BY_TIME = "time"


@dataclass(frozen=True)
class TournamentSettings:
    """Choices made before a tournament: you against 1 to 8 bots.

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
    bot_names: tuple[str, ...] = ()
    """The bots' names, in the order of ``opponents``; empty: automatic."""
    table_size: int = MAX_TABLE_SEATS
    final_table_size: int = MAX_TABLE_SEATS
    """With more players than this, the tournament starts on several tables
    of ``table_size`` seats (V3.1)."""

    def __post_init__(self) -> None:
        check_player_name(self.player_name)

        if not 1 <= len(self.opponents) <= MAX_ENTRANTS - 1:
            raise ValueError(
                f"A tournament has 1 to {MAX_ENTRANTS - 1} bots (you are the "
                f"{MAX_ENTRANTS}th player)."
            )

        for bot in self.opponents:
            get_bot_type(bot)

        if self.bot_names:
            check_bot_names(self.bot_names, len(self.opponents), self.player_name)

        if self.levels_by not in (LEVELS_BY_HANDS, LEVELS_BY_TIME):
            raise ValueError("Levels go up by hands or by time.")

        if self.starting_stack <= 0 or self.buy_in < 0:
            raise ValueError("Invalid starting stack or buy-in.")

        self.tournament_config()  # Checks the structure and the table sizes.

    @property
    def entrants(self) -> int:
        return len(self.opponents) + 1

    @property
    def is_multi_table(self) -> bool:
        return self.entrants > self.final_table_size

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
            table_size=self.table_size,
            final_table_size=self.final_table_size,
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


def check_opponents(opponents: tuple[str, ...]) -> None:
    """1 bot (heads-up) to a full-ring table, each of a known play style."""
    if not 1 <= len(opponents) <= MAX_TABLE_SEATS - 1:
        raise ValueError(f"The number of opponents must be 1 to {MAX_TABLE_SEATS - 1}.")

    for bot in opponents:
        get_bot_type(bot)


def check_bot_names(names: tuple[str, ...], count: int, player_name: str) -> None:
    """One name per bot: distinct, not empty, short, and not yours."""
    if len(names) != count:
        raise ValueError("Every bot needs a name.")

    for name in names:
        if not name.strip():
            raise ValueError("A bot name cannot be empty.")

        if len(name) > MAX_BOT_NAME_LENGTH:
            raise ValueError(
                f"A bot name is at most {MAX_BOT_NAME_LENGTH} characters long."
            )

    if len(set(names)) != len(names):
        raise ValueError("Two bots have the same name.")

    if player_name in names:
        raise ValueError(f"A bot is named {player_name}, like you.")


def bot_names(count: int, taken: Collection[str] = ()) -> list[str]:
    """``count`` distinct bot names, none of them ``taken``: the names of
    ``BOT_NAMES`` then ``MORE_BOT_NAMES``, then numbered ("Alex 2"...)."""
    pool = BOT_NAMES + MORE_BOT_NAMES
    used = set(taken)
    names: list[str] = []
    series = 1

    while len(names) < count:
        for base in pool:
            name = base if series == 1 else f"{base} {series}"

            if name not in used:
                names.append(name)
                used.add(name)

            if len(names) == count:
                break

        series += 1

    return names


def _seat_bots(
    player_name: str,
    opponents: tuple[str, ...],
    rng: random.Random,
    names: tuple[str, ...] = (),
) -> tuple[list[str], dict[str, PlayerController]]:
    """Name the bots (``names``, or automatic names), each with its own
    random generator."""
    names = names or tuple(bot_names(len(opponents), {player_name}))
    controllers: dict[str, PlayerController] = {
        name: create_bot(bot, random.Random(rng.getrandbits(64)))
        for name, bot in zip(names, opponents, strict=True)
    }

    return list(names), controllers


def create_tournament(
    settings: TournamentSettings,
    human_controller: PlayerController,
    rng: random.Random | None = None,
    clock_source: Callable[[], float] | None = None,
) -> Tournament:
    """A tournament opposing the human (first seat, table 1) to bots.

    The hands are kept for the history and the save file. Levels by time
    use a ``LevelClock`` on ``clock_source`` (``time.monotonic`` by default).
    On several tables, the bots are seated in a random order.
    """
    rng = rng or random.Random()
    names, controllers = _seat_bots(
        settings.player_name, settings.opponents, rng, settings.bot_names
    )
    controllers[settings.player_name] = human_controller
    seats = [settings.player_name, *names]
    dealer_index = rng.randrange(len(seats))
    deck_rng = random.Random(rng.getrandbits(64))

    if settings.is_multi_table:
        rng.shuffle(names)
        seats = [settings.player_name, *names]

    return Tournament(
        settings.tournament_config(),
        seats,
        controllers,
        dealer_index=dealer_index,
        deck_rng=deck_rng,
        clock=_clock(settings.levels_by, clock_source),
        keep_hands=True,
        featured=settings.player_name,
    )


def create_spin_and_go(
    settings: SpinSettings,
    human_controller: PlayerController,
    rng: random.Random | None = None,
    clock_source: Callable[[], float] | None = None,
) -> Tournament:
    """A Spin & Go: the multiplier is drawn first, then the hands are dealt."""
    rng = rng or random.Random()
    names, controllers = _seat_bots(settings.player_name, settings.opponents, rng)
    controllers[settings.player_name] = human_controller

    return create_spin(
        SpinConfig(multipliers=settings.multipliers, buy_in=settings.buy_in),
        [settings.player_name, *names],
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
