"""Saved sessions read back as records: results, modes and the library."""

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from backend.application.game_modes import GameMode
from backend.application.hand_records import (
    SessionLibrary,
    load_session_record,
)
from backend.application.persistence import SessionFileError
from backend.poker_engine.constants import Position
from tests.session_files import (
    HUMAN,
    cash_session,
    downgrade_to_version_3,
    tournament_session,
)


def test_a_cash_session_is_read_as_records(tmp_path: Path) -> None:
    path = cash_session(tmp_path / "pk_sess_20261117_093000.dat", hands=10)
    data = json.loads(path.read_text(encoding="utf-8"))

    session = load_session_record(path)

    assert session.mode == GameMode.CASH
    assert session.human == HUMAN
    assert session.started == datetime(2026, 11, 17, 9, 30)
    assert len(session.hands) == 10
    assert session.replayable_hands == 10
    final_stack = data["session"]["players"][0]["stack"]
    assert session.net_chips == final_stack - 1000, "chips won over the hands"
    assert session.chart_points()[0] == (0, 0)
    assert session.chart_points()[-1] == (10, session.net_chips)
    assert session.finish is None


def test_every_hand_has_its_own_cards_and_stacks(tmp_path: Path) -> None:
    session = load_session_record(cash_session(tmp_path / "s.dat", hands=8))

    cards = [hand.hole_cards(HUMAN) for hand in session.hands]
    assert len(set(cards)) == len(cards), "not the last hand's cards everywhere"

    for previous, hand in zip(session.hands, session.hands[1:], strict=False):
        seat = hand.seat(HUMAN)
        before = previous.seat(HUMAN)
        assert seat is not None and before is not None
        assert seat.stack == before.stack + previous.net_result(HUMAN)


def test_a_hand_record_knows_the_chips_of_every_player(tmp_path: Path) -> None:
    session = load_session_record(cash_session(tmp_path / "s.dat", hands=5))

    for hand in session.hands:
        assert sum(hand.net_result(name) for name in hand.players) == 0
        assert hand.pot == sum(hand.payouts.values())
        assert hand.dealer == next(
            seat.name for seat in hand.seats or () if seat.position == Position.BTN
        )


def test_a_tournament_records_the_human_finish(tmp_path: Path) -> None:
    session = load_session_record(tournament_session(tmp_path / "t.dat", seed=3))

    assert session.mode == GameMode.TOURNAMENT
    finish = session.finish
    assert finish is not None
    assert finish.entrants == 3
    assert 1 <= finish.place <= 3
    assert finish.invested == finish.buy_in == 1000


def test_a_spin_and_go_records_its_multiplier(tmp_path: Path) -> None:
    session = load_session_record(tournament_session(tmp_path / "s.dat", spin=True))

    assert session.mode == GameMode.SPIN
    assert session.finish is not None
    assert session.finish.multiplier is not None


def test_older_files_are_read_without_replays(tmp_path: Path) -> None:
    path = cash_session(tmp_path / "old.dat", hands=6)
    current = load_session_record(path)
    downgrade_to_version_3(path)

    old = load_session_record(path)

    assert old.human == HUMAN, "the first seat is the human"
    assert old.mode == GameMode.CASH
    assert old.replayable_hands == 0
    assert old.hand_results() == current.hand_results()
    assert [hand.dealer for hand in old.hands] == [h.dealer for h in current.hands]
    assert [hand.position_of(HUMAN) for hand in old.hands] == [
        hand.position_of(HUMAN) for hand in current.hands
    ]


@pytest.mark.parametrize(
    ("spin", "mode"), [(False, GameMode.TOURNAMENT), (True, GameMode.SPIN)]
)
def test_the_mode_of_an_older_tournament_is_guessed(
    tmp_path: Path, spin: bool, mode: GameMode
) -> None:
    path = tournament_session(tmp_path / "t.dat", spin=spin)
    downgrade_to_version_3(path)

    assert load_session_record(path).mode == mode


def test_an_older_unfinished_tournament_is_told_by_its_rising_blinds(
    tmp_path: Path,
) -> None:
    path = tournament_session(tmp_path / "t.dat", seed=3)
    data = downgrade_to_version_3(path)
    del data["tournament"]
    path.write_text(json.dumps(data), encoding="utf-8")

    session = load_session_record(path)

    assert session.mode == GameMode.TOURNAMENT
    assert session.finish is None


def test_a_file_with_a_broken_hand_is_reported(tmp_path: Path) -> None:
    path = cash_session(tmp_path / "s.dat", hands=2)
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["hands"][1]["actions"]
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SessionFileError, match="s.dat"):
        load_session_record(path)


def test_the_library_lists_the_most_recent_first(tmp_path: Path) -> None:
    cash_session(tmp_path / "pk_sess_20261101_100000.dat", hands=2)
    tournament_session(tmp_path / "pk_sess_20261103_100000.dat")
    cash_session(tmp_path / "pk_sess_20261102_100000.dat", hands=3)
    (tmp_path / "pk_sess_20261104_100000.dat").write_text("{", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not a session", encoding="utf-8")

    scan = SessionLibrary(tmp_path).scan()

    assert [s.started.day for s in scan.sessions] == [3, 2, 1]
    assert len(scan.unreadable) == 1
    assert "pk_sess_20261104_100000.dat" in scan.unreadable[0]


def test_the_library_reads_a_file_again_only_when_it_changed(tmp_path: Path) -> None:
    path = cash_session(tmp_path / "s.dat", hands=2)
    library = SessionLibrary(tmp_path)
    first = library.scan().sessions[0]

    assert library.scan().sessions[0] is first

    cash_session(path, hands=4, seed=2)
    status = path.stat()
    os.utime(path, ns=(status.st_atime_ns, status.st_mtime_ns + 1_000_000_000))

    assert len(library.scan().sessions[0].hands) == 4


def test_an_empty_or_missing_folder_has_no_sessions(tmp_path: Path) -> None:
    assert SessionLibrary(tmp_path / "missing").scan().sessions == ()
    assert SessionLibrary(tmp_path).scan().sessions == ()
