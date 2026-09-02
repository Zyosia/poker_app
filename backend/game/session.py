# game/session.py

from __future__ import annotations

from dataclasses import dataclass

from game.models import Player, Table


@dataclass(frozen=True)
class GameConfig:
    """Configuration of a poker session."""

    starting_stack: int = 1000
    rebuy_stack: int = 500
    small_blind: int = 5
    big_blind: int = 10
    max_players: int = 6

    def __post_init__(self) -> None:
        if self.starting_stack <= 0:
            raise ValueError(
                "Starting stack must be positive."
            )

        if self.rebuy_stack <= 0:
            raise ValueError(
                "Rebuy stack must be positive."
            )

        if self.small_blind <= 0:
            raise ValueError(
                "Small blind must be positive."
            )

        if self.big_blind <= self.small_blind:
            raise ValueError(
                "Big blind must be greater than "
                "small blind."
            )

        if self.max_players < 2:
            raise ValueError(
                "A table must allow at least 2 players."
            )


class GameSession:
    """
    A complete poker session.

    A session contains multiple hands.
    """

    def __init__(
        self,
        players: list[Player],
        config: GameConfig,
    ) -> None:
        self.players = players
        self.config = config

        self.table = Table(
            players=players,
        )

        self.hand_number = 0

    #TODO: Duplicated function (also in models.py)
    def get_players_with_chips(self) -> list[Player]:
        """Return players who have not busted."""

        return [
            player
            for player in self.players
            if (
                not player.eliminated
                and not player.is_busted
            )
        ]

    def can_continue(self) -> bool:
        """
        A poker session can continue while at least
        two players have chips.
        """

        return len(
            self.get_players_with_chips()
        ) >= 2

    def get_busted_players(self) -> list[Player]:
        """Return players who have no chips remaining."""

        return [
            player
            for player in self.players
            if player.is_busted and not player.eliminated
        ]
    
    def rebuy_player(
        self,
        player: Player,
    ) -> None:
        """Give a busted player a new stack."""

        if not player.is_busted:
            raise ValueError(
                f"{player.name} is not busted."
            )

        player.stack = self.config.rebuy_stack


def create_session(
    player_names: list[str],
    config: GameConfig,
) -> GameSession:
    """Create a new poker session."""

    if len(player_names) < 2:
        raise ValueError(
            "At least 2 players are required."
        )

    if len(player_names) > config.max_players:
        raise ValueError(
            "Too many players."
        )

    if len(set(player_names)) != len(player_names):
        raise ValueError(
            "Player names must be unique."
        )

    players = [
        Player(
            name=name,
            stack=config.starting_stack,
        )
        for name in player_names
    ]

    return GameSession(
        players=players,
        config=config,
    )