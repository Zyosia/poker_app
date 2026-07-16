# game/session.py
from game.models import Player, Table


class GameConfig:
    def __init__(
        self,
        starting_stack=1000,
        small_blind=5,
        big_blind=10,
        max_players=6
    ):
        self.starting_stack = starting_stack
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.max_players = max_players


def create_session(player_names, config):
    table = Table()

    for name in player_names:
        player = Player(
            name=name,
            stack=config.starting_stack
        )

        table.players.append(player)

    return table