from backend.game.models import Hand, Player
from backend.game.session import GameConfig, GameSession

# ============================================================
# Helpers
# ============================================================


def make_session(
    *players: Player,
) -> GameSession:
    """Create a minimal game session."""

    session = GameSession(
        players=list(players),
        config=GameConfig(),
    )

    return session


def make_player(
    name: str = "player1",
    stack: int = 100,
) -> Player:
    """Create a player."""

    return Player(
        name=name,
        stack=stack,
    )


def make_hand(
    session: GameSession,
    *,
    current_bet: int = 0,
) -> Hand:
    """Create a hand with a configurable current bet."""

    hand = Hand(
        table=session.table,
    )

    hand.current_bet = current_bet

    return hand
