"""Saved session files for the tests of the V1.1 tools, played by bots.

The "human" seat is played by a bot too, so a whole session plays without
any decision from a test; the file still names it as the human.
"""

import json
import random
from pathlib import Path
from typing import Any

from backend.application.game_modes import GameMode
from backend.application.persistence import save_session
from backend.application.setup import (
    GameSettings,
    SpinSettings,
    TournamentSettings,
    create_game,
    create_spin_and_go,
    create_tournament,
)
from backend.bots.basic_bot import BasicBot

HUMAN = "Hero"


def cash_session(path: Path, hands: int = 12, seed: int = 1) -> Path:
    """A cash game of ``hands`` hands between Hero and three bots."""
    random.seed(seed)  # The engine deals from the global RNG by default.
    game = create_game(
        GameSettings(player_name=HUMAN, opponent_count=3),
        human_controller=BasicBot(random.Random(seed)),
        rng=random.Random(seed),
    )

    for _ in range(hands):
        if not game.can_start_hand():
            break

        game.start_hand()

        while game.is_hand_in_progress:
            game.step()

    return save_session(game.session, path, human=HUMAN, mode=GameMode.CASH)


def tournament_session(path: Path, seed: int = 1, spin: bool = False) -> Path:
    """A finished tournament (or Spin & Go) where Hero is played by a bot."""
    bot = BasicBot(random.Random(seed))
    rng = random.Random(seed)

    if spin:
        tournament = create_spin_and_go(SpinSettings(player_name=HUMAN), bot, rng)
    else:
        settings = TournamentSettings(player_name=HUMAN, opponents=("tag", "lag"))
        tournament = create_tournament(settings, bot, rng)

    result = tournament.play_to_end()

    return save_session(
        tournament.session,
        path,
        tournament=result.to_dict(),
        human=HUMAN,
        mode=GameMode.SPIN if spin else GameMode.TOURNAMENT,
    )


def downgrade_to_version_3(path: Path) -> dict[str, Any]:
    """Rewrite a saved file as format 3 saved it: no seats, human or mode."""
    data = json.loads(path.read_text(encoding="utf-8"))
    data["format_version"] = 3
    del data["human"], data["mode"]

    for hand in data["hands"]:
        del hand["seats"]

    path.write_text(json.dumps(data), encoding="utf-8")

    return data
