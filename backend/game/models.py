# game/models.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from game.constants import (
    ActionType,
    Card,
    Position,
    Street,
)

if TYPE_CHECKING:
    from game.deck import Deck
    from game.hand_evaluator import HandEvaluation


@dataclass
class Player:
    name: str
    stack: int

    hand: list[Card] = field(
        default_factory=list,
    )

    position: Position | None = None

    # Amount invested during the current street.
    current_bet: int = 0

    # Total amount invested during the current hand.
    #
    # This value is intentionally never reset between
    # streets. It is used to build main pots and side pots.
    total_contribution: int = 0

    folded: bool = False
    all_in: bool = False

    acted_this_round: bool = False

    eliminated: bool = False

    def reset_for_new_hand(self) -> None:
        """Reset all state belonging to a single hand."""

        self.hand.clear()

        self.position = None

        self.current_bet = 0
        self.total_contribution = 0

        self.folded = False
        self.all_in = False

        self.acted_this_round = False

    @property
    def is_busted(self) -> bool:
        """Return True when the player has no chips left."""

        return self.stack <= 0

    @property
    def is_active(self) -> bool:
        """
        Return True when the player is still involved
        in the current hand.

        An all-in player is still active.
        """

        return not self.folded

    @property
    def can_act(self) -> bool:
        """Return True when the player can perform an action."""

        return (
            self.is_active
            and not self.all_in
        )

    def __str__(self) -> str:
        return f"{self.name} ({self.stack})"


@dataclass
class Table:
    players: list[Player]

    dealer_index: int = 0

    def get_players_with_chips(self) -> list[Player]:
        """Return players who have chips remaining."""

        return [
            player
            for player in self.players
            if (
                not player.eliminated
                and not player.is_busted
            )
        ]

    def get_active_players(self) -> list[Player]:
        """
        Return players still involved in the current hand.

        Folded players are excluded.
        All-in players remain included.
        """

        return [
            player
            for player in self.players
            if player.is_active
        ]

    def move_dealer(self) -> None:
        """Move the dealer button to the next player with chips."""

        players_with_chips = self.get_players_with_chips()

        if len(players_with_chips) <= 1:
            return

        player_count = len(self.players)

        for _ in range(player_count):
            self.dealer_index = (
                self.dealer_index + 1
            ) % player_count

            if self.players[
                self.dealer_index
            ].is_busted is False:
                return

        raise RuntimeError(
            "Could not find a valid dealer."
        )

    @property
    def dealer(self) -> Player:
        return self.players[self.dealer_index]


@dataclass(frozen=True)
class PotResult:
    """
    Result of distributing one pot.
    """

    amount: int

    eligible_players: tuple[str, ...]

    winners: tuple[str, ...]

    decisive_tiebreaker: str | None = None

    decisive_value: int | None = None


@dataclass
class Hand:
    """State of a single Texas Hold'em hand."""

    table: Table

    deck: Deck | None = None

    community_cards: list[Card] = field(
        default_factory=list,
    )

    pot: int = 0

    street: Street = "PREFLOP"

    current_bet: int = 0

    last_raise_size: int = 0

    last_raiser: Player | None = None

    first_to_act: Player | None = None

    current_player: Player | None = None

    last_player_to_act: Player | None = None

    winner_by_fold: Player | None = None

    showdown_evaluations: dict[
        str,
        HandEvaluation,
    ] = field(
        default_factory=dict,
    )

    payouts: dict[str, int] = field(
        default_factory=dict,
    )

    pot_results: list[PotResult] = field(
        default_factory=list,
    )

    finished: bool = False

    def reset_street_betting(self) -> None:
        """Reset betting state for a new street."""

        self.current_bet = 0
        self.last_raise_size = 0
        self.last_raiser = None
        self.current_player = None
        self.last_player_to_act = None

        for player in self.table.players:
            player.current_bet = 0
            player.acted_this_round = False