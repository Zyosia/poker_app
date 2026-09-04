from dataclasses import dataclass, field

from .constants import (
    Card,
    Position,
    Street,
)
from .deck import Deck
from .hand_evaluator import HandEvaluation


@dataclass(frozen=True)
class ActionEvent:
    """Record of one action performed during a poker hand."""

    sequence: int
    street: Street
    player: str
    position: Position | None
    action: str
    amount: int
    bet_before: int
    bet_after: int
    pot_after: int
    current_bet_after: int
    bet_initiator: bool = False


@dataclass(frozen=True)
class StreetEvent:
    """Record of a street transition."""

    street: Street
    community_cards: tuple[Card, ...]


@dataclass(frozen=True)
class PotEvent:
    """Snapshot of the pot during a hand."""

    sequence: int
    street: Street
    amount: int


@dataclass
class Player:
    name: str
    stack: int

    hand: list[Card] = field(
        default_factory=list,
    )

    position: Position | None = None

    current_bet: int = 0

    total_contribution: int = 0

    folded: bool = False
    all_in: bool = False

    acted_this_round: bool = False

    eliminated: bool = False

    def reset_for_new_hand(self) -> None:
        self.hand.clear()

        self.position = None

        self.current_bet = 0
        self.total_contribution = 0

        self.folded = False
        self.all_in = False

        self.acted_this_round = False

    @property
    def is_busted(self) -> bool:
        return self.stack <= 0

    @property
    def is_eliminated(self) -> bool:
        return self.eliminated

    @property
    def is_active(self) -> bool:
        return not self.folded

    @property
    def can_act(self) -> bool:
        return self.is_active and not self.all_in

    def __str__(self) -> str:
        return f"{self.name} ({self.stack})"


@dataclass
class Table:
    players: list[Player]

    dealer_index: int = 0

    def get_players_with_chips(self) -> list[Player]:
        return [
            player
            for player in self.players
            if (not player.is_eliminated and not player.is_busted)
        ]

    def get_active_players(self) -> list[Player]:
        return [player for player in self.players if player.is_active]

    def move_dealer(self) -> None:
        players_with_chips = self.get_players_with_chips()

        if len(players_with_chips) <= 1:
            return

        player_count = len(self.players)

        for _ in range(player_count):
            self.dealer_index = (self.dealer_index + 1) % player_count

            if self.players[self.dealer_index].is_busted is False:
                return

        raise RuntimeError("Could not find a valid dealer.")

    @property
    def dealer(self) -> Player:
        return self.players[self.dealer_index]


@dataclass(frozen=True)
class PotResult:
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

    actions: list[ActionEvent] = field(
        default_factory=list,
    )

    streets: list[StreetEvent] = field(
        default_factory=list,
    )

    pot_history: list[PotEvent] = field(
        default_factory=list,
    )

    finished: bool = False

    def reset_street_betting(self) -> None:
        self.current_bet = 0
        self.last_raise_size = 0
        self.last_raiser = None
        self.current_player = None
        self.last_player_to_act = None

        for player in self.table.players:
            player.current_bet = 0
            player.acted_this_round = False
