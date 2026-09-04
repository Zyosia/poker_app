import json

from backend.data_handler.handler import (
    save_session,
    serialize_hand,
    serialize_session,
)
from backend.game.history import (
    record_action,
    record_street,
)
from backend.game.models import Hand
from tests.history.history_test_config import make_session_with_hand


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

    hand.street = "FLOP"
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
