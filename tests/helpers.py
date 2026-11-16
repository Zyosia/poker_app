"""Shared helpers for the test suite."""

from collections.abc import Iterable

from backend.poker_engine.actions import Action
from backend.poker_engine.betting import (
    apply_action,
    begin_betting_round,
    get_legal_actions,
)
from backend.poker_engine.constants import ActionType, Street
from backend.poker_engine.hand import ActionChooser
from backend.poker_engine.models import Hand, Player
from backend.poker_engine.session import GameConfig, GameSession, create_session

ActionSpec = tuple[str, int | None]


def make_session(*players: Player) -> GameSession:
    """Create a minimal game session."""
    return GameSession(players=list(players), config=GameConfig())


def make_player(name: str = "player1", stack: int = 100) -> Player:
    """Create a player."""
    return Player(name=name, stack=stack)


def make_hand(session: GameSession, *, current_bet: int = 0) -> Hand:
    """Create a hand with a configurable current bet."""
    hand = Hand(table=session.table)
    hand.current_bet = current_bet

    return hand


def make_session_with_hand() -> tuple[GameSession, Hand]:
    """Create a three-player session with Alice on the button and a new hand."""
    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(starting_stack=1000, small_blind=5, big_blind=10),
    )
    session.table.dealer_index = 0

    hand = Hand(table=session.table)
    hand.street = Street.PREFLOP

    return session, hand


def to_action(spec: ActionSpec) -> Action:
    """Convert an ("action", amount) pair into an engine action."""
    action_type, amount = spec

    return Action(type=ActionType(action_type), amount=amount)


def scripted_actions(specs: Iterable[ActionSpec]) -> ActionChooser:
    """Return a chooser playing the given actions in order, whoever acts."""
    iterator = iter(specs)

    def choose_action(hand: Hand, player: Player) -> Action:
        return to_action(next(iterator))

    return choose_action


def play_betting_round(
    hand: Hand,
    specs: Iterable[ActionSpec],
) -> tuple[list[Player], bool]:
    """Run one betting round with scripted actions.

    Returns the players who acted, in order, and whether the round completed
    normally (False when the hand ended because everyone else folded).
    """
    iterator = iter(specs)
    players_who_acted: list[Player] = []

    begin_betting_round(hand)

    while hand.current_player is not None:
        players_who_acted.append(hand.current_player)
        apply_action(hand, to_action(next(iterator)))

    return players_who_acted, hand.winner_by_fold is None


def allowed_action_types(player: Player, hand: Hand) -> list[str]:
    """Return the types of the actions currently legal for a player."""
    return [action.type.value for action in get_legal_actions(player=player, hand=hand)]
