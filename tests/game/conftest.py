from collections.abc import Iterator

import pytest

from backend.game.controllers import HumanController
from backend.game.models.models import Hand, Player
from backend.game.models.session import GameConfig, GameSession

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
        controller=HumanController(),
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


def mock_actions(
    monkeypatch: pytest.MonkeyPatch,
    actions: list[tuple[str, int | None]],
) -> None:
    """Mock player actions in the order requested by the engine."""

    action_iterator: Iterator[tuple[str, int | None]] = iter(actions)

    def fake_ask_player_action(
        player,
        hand,
        allowed_actions,
    ) -> tuple[str, int | None]:
        return next(action_iterator)

    monkeypatch.setattr(
        "backend.game.engine.betting.ask_player_action",
        fake_ask_player_action,
    )

    monkeypatch.setattr(
        "backend.game.engine.betting.display_table",
        lambda **_: None,
    )
