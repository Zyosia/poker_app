"""Saving of poker sessions and their hand history as JSON files."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.poker_engine.models import Hand, Player
from backend.poker_engine.session import GameSession

SESSION_DIR = Path(__file__).resolve().parents[1] / "data" / "sessions"


def serialize_player(player: Player) -> dict[str, Any]:
    """Serialize persistent player state."""
    return {
        "name": player.name,
        "stack": player.stack,
        "eliminated": player.eliminated,
    }


def serialize_hand(hand: Hand, hand_number: int) -> dict[str, Any]:
    """Serialize one poker hand."""
    return {
        "hand_number": hand_number,
        "dealer": hand.table.dealer.name,
        "dealer_index": hand.table.dealer_index,
        "players": [
            {
                "name": player.name,
                "position": player.position,
                "stack": player.stack,
                "hole_cards": list(player.hand),
                "folded": player.folded,
                "all_in": player.all_in,
                "total_contribution": player.total_contribution,
            }
            for player in hand.table.players
        ],
        "actions": [asdict(event) for event in hand.actions],
        "streets": [asdict(event) for event in hand.streets],
        "pot_history": [asdict(event) for event in hand.pot_history],
        "pot_results": [asdict(result) for result in hand.pot_results],
        "showdown": {
            player_name: {
                "rank": evaluation.rank,
                "name": evaluation.name,
                "cards": list(evaluation.cards),
                "tiebreaker": list(evaluation.tiebreaker),
            }
            for player_name, evaluation in hand.showdown_evaluations.items()
        },
        "winner_by_fold": (
            hand.winner_by_fold.name if hand.winner_by_fold is not None else None
        ),
        "payouts": dict(hand.payouts),
        "finished": hand.finished,
    }


def serialize_session(session: GameSession) -> dict[str, Any]:
    """Serialize the complete poker session.

    Player state inside a hand reflects the latest hand only, because players
    are reused from one hand to the next.
    """
    return {
        "session": {
            "hand_count": session.hand_number,
            "config": asdict(session.config),
            "players": [serialize_player(player) for player in session.players],
        },
        "hands": [
            serialize_hand(hand=hand, hand_number=index)
            for index, hand in enumerate(session.hands, start=1)
        ],
    }


def new_session_file_path(directory: Path = SESSION_DIR) -> Path:
    """Return a timestamped file path for a new session."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return directory / f"pk_sess_{timestamp}.dat"


def save_session(session: GameSession, file_path: Path | None = None) -> Path:
    """Write the current state of a session, replacing any previous save.

    The data is written to a temporary file first so an interrupted save
    never corrupts the existing file.
    """
    if file_path is None:
        file_path = new_session_file_path()

    file_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = file_path.with_suffix(".tmp")

    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(serialize_session(session), file, indent=4, ensure_ascii=False)

    temporary_path.replace(file_path)

    return file_path
