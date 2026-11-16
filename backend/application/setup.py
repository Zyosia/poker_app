"""Creation of a game from the settings chosen by the user."""

import random
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from backend.bots.basic_bot import BasicBot
from backend.bots.random_bot import RandomBot
from backend.poker_engine.constants import MAX_TABLE_SEATS
from backend.poker_engine.session import GameConfig, create_session

from .controllers import PlayerController
from .game import PokerGame

BOT_NAMES = ("Alex", "Bella", "Carlos", "Dana", "Elio", "Fiona")


class BotLevel(StrEnum):
    EASY = "easy"
    NORMAL = "normal"


@dataclass(frozen=True)
class GameSettings:
    """Choices made by the user before starting a game."""

    player_name: str = "Hero"
    opponent_count: int = 3
    bot_level: BotLevel = BotLevel.NORMAL
    starting_stack: int = 1000
    small_blind: int = 5
    big_blind: int = 10

    def __post_init__(self) -> None:
        if not self.player_name.strip():
            raise ValueError("The player name cannot be empty.")

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
