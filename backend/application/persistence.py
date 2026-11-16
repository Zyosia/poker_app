"""Saving and loading of poker sessions and their hand history (JSON files).

File format versions:

- **1** (Alpha 1.2 to Beta 1.1): no ``format_version`` field; the blinds
  are only in the session configuration and there are no antes.
- **2** (V1.0): ``format_version`` is 2; the session and every hand record
  their blind level (blinds, ante, ante type), every hand its
  ``dead_money`` (big-blind ante), and ``post_ante`` actions can appear in
  the history. A tournament session also stores its results under
  ``tournament``.

``load_session_file`` reads both versions and returns version 2 data.
"""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.poker_engine.blinds import BlindLevel
from backend.poker_engine.models import Hand, Player
from backend.poker_engine.session import GameSession

SESSION_DIR = Path(__file__).resolve().parents[1] / "data" / "sessions"

FORMAT_VERSION = 2
SUPPORTED_FORMAT_VERSIONS = (1, 2)


class SessionFileError(ValueError):
    """A session file cannot be read: unknown version or invalid content."""


def serialize_blind_level(level: BlindLevel) -> dict[str, Any]:
    return asdict(level)


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
        "blind_level": (
            serialize_blind_level(hand.blind_level)
            if hand.blind_level is not None
            else None
        ),
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
        "dead_money": hand.dead_money,
        "payouts": dict(hand.payouts),
        "finished": hand.finished,
    }


def serialize_session(
    session: GameSession, tournament: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Serialize the complete poker session.

    Player state inside a hand reflects the latest hand only, because players
    are reused from one hand to the next. ``tournament`` holds the results of
    a tournament session.
    """
    data: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "session": {
            "hand_count": session.hand_number,
            "config": asdict(session.config),
            "blind_level": serialize_blind_level(session.blind_level),
            "players": [serialize_player(player) for player in session.players],
        },
        "hands": [
            serialize_hand(hand=hand, hand_number=index)
            for index, hand in enumerate(session.hands, start=1)
        ],
    }

    if tournament is not None:
        data["tournament"] = tournament

    return data


def new_session_file_path(directory: Path = SESSION_DIR) -> Path:
    """Return a timestamped file path for a new session."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return directory / f"pk_sess_{timestamp}.dat"


def save_session(
    session: GameSession,
    file_path: Path | None = None,
    tournament: dict[str, Any] | None = None,
) -> Path:
    """Write the current state of a session, replacing any previous save.

    The data is written to a temporary file first so an interrupted save
    never corrupts the existing file.
    """
    if file_path is None:
        file_path = new_session_file_path()

    file_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = file_path.with_suffix(".tmp")

    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(
            serialize_session(session, tournament=tournament),
            file,
            indent=4,
            ensure_ascii=False,
        )

    temporary_path.replace(file_path)

    return file_path


def load_session_file(file_path: Path) -> dict[str, Any]:
    """Read a saved session, of any supported format version.

    Version 1 files are upgraded in memory to version 2: the blinds of the
    configuration become the blind level of the session and of every hand,
    with no ante. Raises ``SessionFileError`` with a clear message for an
    unknown version or a file that is not a session.
    """
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SessionFileError(
            f"{file_path.name} is not a readable session file: {error}"
        ) from error

    if not isinstance(data, dict) or "session" not in data or "hands" not in data:
        raise SessionFileError(f"{file_path.name} is not a poker session file.")

    version = data.get("format_version", 1)

    if version not in SUPPORTED_FORMAT_VERSIONS:
        supported = ", ".join(str(v) for v in SUPPORTED_FORMAT_VERSIONS)
        raise SessionFileError(
            f"{file_path.name} uses session format version {version}; "
            f"this version of the application reads versions {supported}."
        )

    if version == 1:
        _upgrade_from_version_1(data)

    return data


def _upgrade_from_version_1(data: dict[str, Any]) -> None:
    config = data["session"]["config"]
    level = serialize_blind_level(
        BlindLevel(small_blind=config["small_blind"], big_blind=config["big_blind"])
    )
    data["format_version"] = FORMAT_VERSION
    data["session"]["blind_level"] = level

    for hand in data["hands"]:
        hand["blind_level"] = dict(level)
        hand["dead_money"] = 0
