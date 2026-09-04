from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.game.models import Player
from backend.game.session import GameSession

SESSION_DIR = Path("backend/data/sessions")


def serialize_player(
    player: Player,
) -> dict:
    """Serialize persistent player state."""

    return {
        "name": player.name,
        "stack": player.stack,
        "eliminated": player.eliminated,
    }


def serialize_hand(
    hand,
    hand_number: int,
) -> dict:
    """Serialize one completed poker hand."""

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


def serialize_session(
    session: GameSession,
) -> dict:
    """Serialize the complete poker session."""

    return {
        "session": {
            "hand_count": session.hand_number,
            "config": {
                "starting_stack": session.config.starting_stack,
                "rebuy_stack": session.config.rebuy_stack,
                "small_blind": session.config.small_blind,
                "big_blind": session.config.big_blind,
                "max_players": session.config.max_players,
            },
            "players": [serialize_player(player) for player in session.players],
        },
        "hands": [
            serialize_hand(
                hand=hand,
                hand_number=index,
            )
            for index, hand in enumerate(
                session.hands,
                start=1,
            )
        ],
    }


def save_session(
    session: GameSession,
    file_path: Path | None = None,
) -> Path:
    """
    Persist the current state of a poker session.

    The file is rewritten after each completed hand.
    """

    SESSION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if file_path is None:
        timestamp = datetime.now(ZoneInfo("Europe/Paris")).strftime(
            "%Y%m%d_%H%M%S",
        )

        file_path = SESSION_DIR / f"pk_sess_{timestamp}.dat"

    temporary_path = file_path.with_suffix(".tmp")

    session_data = serialize_session(
        session,
    )

    with temporary_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            session_data,
            file,
            indent=4,
            ensure_ascii=False,
        )

    temporary_path.replace(
        file_path,
    )

    return file_path
