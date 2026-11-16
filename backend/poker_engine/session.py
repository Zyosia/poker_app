"""A poker session: configuration, players and the hands they play."""

from dataclasses import dataclass

from .blinds import BlindLevel
from .constants import MAX_TABLE_SEATS
from .models import Hand, Player, Table


@dataclass(frozen=True)
class GameConfig:
    """Configuration of a poker session."""

    starting_stack: int = 1000
    rebuy_stack: int = 500
    small_blind: int = 5
    big_blind: int = 10
    max_players: int = MAX_TABLE_SEATS

    def __post_init__(self) -> None:
        if self.starting_stack <= 0:
            raise ValueError("Starting stack must be positive.")

        if self.rebuy_stack <= 0:
            raise ValueError("Rebuy stack must be positive.")

        if self.small_blind <= 0:
            raise ValueError("Small blind must be positive.")

        if self.big_blind <= self.small_blind:
            raise ValueError("Big blind must be greater than small blind.")

        if not 2 <= self.max_players <= MAX_TABLE_SEATS:
            raise ValueError(f"A table must allow 2 to {MAX_TABLE_SEATS} players.")


class GameSession:
    """A complete poker session, made of consecutive hands."""

    def __init__(self, players: list[Player], config: GameConfig) -> None:
        self.players = players
        self.config = config
        self.table = Table(players=players)
        self.hand_number = 0
        self.hands: list[Hand] = []
        self.blind_level = BlindLevel(
            small_blind=config.small_blind, big_blind=config.big_blind
        )
        """Forced bets of the next hand; a tournament raises them between hands."""

    def set_blind_level(self, level: BlindLevel) -> None:
        """Set the blinds and ante of the next hands, between two hands only."""
        if self.hands and not self.hands[-1].finished:
            raise RuntimeError("The blind level only changes between hands.")

        self.blind_level = level

    def get_players_with_chips(self) -> list[Player]:
        """Return players who can be dealt into the next hand."""
        return self.table.get_players_with_chips()

    def can_continue(self) -> bool:
        """A session continues while at least two players have chips."""
        return len(self.get_players_with_chips()) >= 2

    def get_busted_players(self) -> list[Player]:
        """Return players without chips who have not been eliminated yet."""
        return [
            player
            for player in self.players
            if player.is_busted and not player.is_eliminated
        ]

    def rebuy_player(self, player: Player) -> None:
        """Give a busted player a new stack."""
        if not player.is_busted:
            raise ValueError(f"{player.name} is not busted.")

        player.stack = self.config.rebuy_stack
        player.eliminated = False

    def eliminate_player(self, player: Player) -> None:
        """Remove a busted player from the session."""
        if not player.is_busted:
            raise ValueError(f"{player.name} still has chips.")

        player.eliminated = True


def create_session(player_names: list[str], config: GameConfig) -> GameSession:
    """Create a new poker session."""
    if len(player_names) < 2:
        raise ValueError("At least 2 players are required.")

    if len(player_names) > config.max_players:
        raise ValueError("Too many players.")

    if len(set(player_names)) != len(player_names):
        raise ValueError("Player names must be unique.")

    players = [Player(name=name, stack=config.starting_stack) for name in player_names]

    return GameSession(players=players, config=config)
