import json
from pathlib import Path

import pytest

from backend.application.persistence import (
    FORMAT_VERSION,
    SessionFileError,
    load_session_file,
    save_session,
    serialize_hand,
    serialize_session,
)
from backend.poker_engine.actions import Action
from backend.poker_engine.blinds import AnteType, BlindLevel
from backend.poker_engine.constants import ActionType, Street
from backend.poker_engine.hand import play_hand
from backend.poker_engine.history import (
    record_action,
    record_street,
)
from backend.poker_engine.models import Hand
from backend.poker_engine.session import GameConfig, GameSession, create_session
from tests.helpers import make_session_with_hand


def test_serialize_hand_contains_history():
    session, hand = make_session_with_hand()

    player = session.players[0]

    player.current_bet = 10
    hand.current_bet = 10
    hand.pot = 30

    record_action(
        hand=hand,
        player=player,
        action="call",
        amount=10,
        bet_before=0,
    )

    hand.street = Street.FLOP
    hand.community_cards.extend(
        ("AS", "KD", "7C"),
    )

    record_street(hand)

    data = serialize_hand(
        hand=hand,
        hand_number=1,
    )

    assert data["hand_number"] == 1
    assert data["dealer"] == "Alice"
    assert data["dealer_index"] == 0

    assert len(data["actions"]) == 1
    assert data["actions"][0]["player"] == "Alice"
    assert data["actions"][0]["action"] == "call"

    assert len(data["streets"]) == 1
    assert data["streets"][0]["street"] == "FLOP"
    assert data["streets"][0]["community_cards"] == (
        "AS",
        "KD",
        "7C",
    )


def test_serialize_session_contains_all_hands():
    session, hand = make_session_with_hand()

    session.hand_number = 1
    session.hands.append(hand)

    data = serialize_session(session)

    assert data["session"]["hand_count"] == 1
    assert len(data["hands"]) == 1
    assert data["hands"][0]["hand_number"] == 1


def test_serialize_session_supports_multiple_hands():
    session, hand1 = make_session_with_hand()

    hand2 = Hand(
        table=session.table,
    )

    session.hand_number = 2
    session.hands.extend(
        [hand1, hand2],
    )

    data = serialize_session(session)

    assert len(data["hands"]) == 2
    assert data["hands"][0]["hand_number"] == 1
    assert data["hands"][1]["hand_number"] == 2


def test_save_session_creates_valid_json_file(tmp_path):
    session, hand = make_session_with_hand()

    session.hand_number = 1
    session.hands.append(hand)

    file_path = tmp_path / "pk_sess_test.dat"

    saved_path = save_session(
        session=session,
        file_path=file_path,
    )

    assert saved_path == file_path
    assert file_path.exists()

    with file_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    assert data["session"]["hand_count"] == 1
    assert len(data["hands"]) == 1


def test_save_session_overwrites_existing_file(tmp_path):
    session, hand1 = make_session_with_hand()

    session.hand_number = 1
    session.hands.append(hand1)

    file_path = tmp_path / "pk_sess_test.dat"

    save_session(
        session=session,
        file_path=file_path,
    )

    hand2 = Hand(
        table=session.table,
    )

    session.hand_number = 2
    session.hands.append(hand2)

    save_session(
        session=session,
        file_path=file_path,
    )

    with file_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    assert data["session"]["hand_count"] == 2
    assert len(data["hands"]) == 2


def test_serialized_session_preserves_dealer_information():
    session, hand = make_session_with_hand()

    session.hand_number = 1
    session.hands.append(hand)

    data = serialize_session(session)

    serialized_hand = data["hands"][0]

    assert serialized_hand["dealer"] == "Alice"
    assert serialized_hand["dealer_index"] == 0


# --- Format version 2 and loading -----------------------------------------


def antes_session() -> GameSession:
    session = create_session(
        player_names=["Alice", "Bob", "Charlie"], config=GameConfig()
    )
    session.table.dealer_index = 0
    session.set_blind_level(BlindLevel(10, 20, ante=20, ante_type=AnteType.BIG_BLIND))
    play_hand(session, lambda hand, player: Action(type=ActionType.FOLD))

    return session


def test_saved_sessions_are_format_version_2_with_blind_levels(tmp_path: Path) -> None:
    path = save_session(antes_session(), tmp_path / "session.dat")
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["format_version"] == FORMAT_VERSION == 2
    assert data["session"]["blind_level"] == {
        "small_blind": 10,
        "big_blind": 20,
        "ante": 20,
        "ante_type": "big_blind",
    }
    hand = data["hands"][0]
    assert hand["blind_level"]["ante"] == 20
    assert hand["dead_money"] == 20
    assert ("Charlie", "post_ante", 20) in [
        (action["player"], action["action"], action["amount"])
        for action in hand["actions"]
    ]


def test_a_saved_session_loads_back(tmp_path: Path) -> None:
    path = save_session(antes_session(), tmp_path / "session.dat")

    assert load_session_file(path) == json.loads(path.read_text(encoding="utf-8"))


def test_a_version_1_file_loads_and_is_upgraded(tmp_path: Path) -> None:
    data = serialize_session(antes_session())
    del data["format_version"]
    del data["session"]["blind_level"]
    data["session"]["config"]["small_blind"] = 5
    data["session"]["config"]["big_blind"] = 10

    for hand in data["hands"]:
        del hand["blind_level"], hand["dead_money"]

    path = tmp_path / "old.dat"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = load_session_file(path)

    assert loaded["format_version"] == 2
    expected_level = {
        "small_blind": 5,
        "big_blind": 10,
        "ante": 0,
        "ante_type": "classic",
    }
    assert loaded["session"]["blind_level"] == expected_level
    assert loaded["hands"][0]["blind_level"] == expected_level
    assert loaded["hands"][0]["dead_money"] == 0


def test_an_unknown_version_is_rejected_clearly(tmp_path: Path) -> None:
    data = serialize_session(antes_session())
    data["format_version"] = 99
    path = tmp_path / "future.dat"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SessionFileError, match="version 99.*reads versions 1, 2"):
        load_session_file(path)


@pytest.mark.parametrize("content", ["not json", "[1, 2]", '{"hands": []}'])
def test_files_that_are_not_sessions_are_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "broken.dat"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(SessionFileError, match="broken.dat"):
        load_session_file(path)
