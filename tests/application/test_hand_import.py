"""PokerStars and Winamax hand histories, dealt again through the engine."""

from datetime import datetime
from pathlib import Path

import pytest

from backend.application.game_modes import GameMode
from backend.application.hand_import import read_hand_history_file
from backend.application.hand_records import HandRecord
from backend.application.persistence import SessionFileError
from backend.application.replay import HandReplay
from backend.poker_engine.blinds import AnteType
from backend.poker_engine.constants import Position
from backend.poker_engine.hand_evaluator import evaluate_rank
from backend.simulation.config import SeatSpec, SimulationConfig, StackPolicy
from backend.simulation.runner import run_simulation
from tests.hand_history_text import (
    POKERSTARS_FILE,
    WINAMAX_FILE,
    pokerstars_text,
    winamax_text,
)


def write(tmp_path: Path, text: str, name: str = "history.txt") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")

    return path


# --- PokerStars --------------------------------------------------------------------


def test_a_pokerstars_file_is_read_hand_by_hand(tmp_path: Path) -> None:
    session = read_hand_history_file(write(tmp_path, POKERSTARS_FILE))

    assert session.source == "PokerStars" and session.imported
    assert session.mode == GameMode.CASH
    assert session.human == "Hero"
    assert session.started == datetime(2022, 11, 5, 10, 12, 13)
    assert [hand.hand_id for hand in session.hands] == [
        "PokerStars #241234567890",
        "PokerStars #241234567891",
    ]
    assert len(session.notes) == 2
    assert "241234567892: a blind posted out of turn" in session.notes[0]
    assert "241234567893: only No Limit Hold'em" in session.notes[1]


def test_a_showdown_with_rake_and_a_muck(tmp_path: Path) -> None:
    hand = read_hand_history_file(write(tmp_path, POKERSTARS_FILE)).hands[0]

    assert hand.big_blind == 2, "amounts in cents"
    assert [seat.name for seat in hand.seats or ()] == [
        "Alice",
        "Bob Smith",
        "Hero",
        "Dan",
    ], "Eve was sitting out"
    assert hand.position_of("Hero") == Position.CO
    assert hand.dealer == "Dan"
    assert hand.hole_cards("Hero") == ("9C", "9D")
    assert hand.hidden == {"Alice", "Bob Smith", "Dan"}
    assert dict(hand.payouts) == {"Hero": 161}, "before the 7 cents of rake"
    assert hand.net_result("Hero") == 161 - 80
    hero = evaluate_rank(["9C", "9D", *hand.board])
    bob = hand.hole_cards("Bob Smith")
    assert bob is not None and evaluate_rank([*bob, *hand.board]) < hero


def test_an_uncalled_bet_is_returned(tmp_path: Path) -> None:
    hand = read_hand_history_file(write(tmp_path, POKERSTARS_FILE)).hands[1]

    assert dict(hand.payouts) == {"Dan": 9}
    assert hand.net_result("Dan") == 3
    assert hand.winner_by_fold == "Dan"


def test_imported_hands_replay_in_the_replayer(tmp_path: Path) -> None:
    for hand in read_hand_history_file(write(tmp_path, POKERSTARS_FILE)).hands:
        replay = HandReplay(hand)
        assert replay.hand_at(replay.step_count).finished


# --- Winamax ----------------------------------------------------------------------


def test_a_winamax_tournament_hand_with_seven_players_and_antes(
    tmp_path: Path,
) -> None:
    session = read_hand_history_file(write(tmp_path, WINAMAX_FILE))

    assert session.source == "Winamax"
    assert session.mode == GameMode.TOURNAMENT
    assert session.notes == ()
    hand = session.hands[0]
    assert hand.hand_id == "Winamax #1234567-89-1600000000"
    assert hand.blind_level.ante == 10
    assert hand.blind_level.ante_type == AnteType.CLASSIC
    assert len(hand.players) == 7
    assert hand.position_of("Hero") == Position.UTG
    assert hand.position_of("Max") == Position.LJ
    assert hand.position_of("Joueur Un") == Position.SB
    assert dict(hand.payouts) == {"Hero": 2420}, "the river bet nobody called"
    assert hand.net_result("Hero") == 2420 - (10 + 250 + 400 + 900)
    assert "Ugo" in hand.hidden and "Hero" not in hand.hidden
    HandReplay(hand)


# --- What is refused ---------------------------------------------------------------


def test_a_history_that_does_not_add_up_is_refused(tmp_path: Path) -> None:
    wrong = POKERSTARS_FILE.replace(
        "Bob Smith: calls $0.04\n*** FLOP",
        "Bob Smith: calls $0.05\n*** FLOP",
    )

    session = read_hand_history_file(write(tmp_path, wrong))

    assert [hand.hand_id for hand in session.hands] == ["PokerStars #241234567891"]
    assert "does not put in the chips recorded" in session.notes[0]


def test_winnings_that_differ_are_refused(tmp_path: Path) -> None:
    wrong = WINAMAX_FILE.replace("collected 1520", "collected 1400")

    session = read_hand_history_file(write(tmp_path, wrong))

    assert session.hands == ()
    assert "the winnings are not those of the history" in session.notes[0]


def test_a_file_without_hands_is_not_a_history(tmp_path: Path) -> None:
    with pytest.raises(SessionFileError, match="no PokerStars or Winamax hand"):
        read_hand_history_file(write(tmp_path, "Hello\nnothing here\n"))


# --- Round trip: the engine's own hands, written as the sites write them ------------


def simulated_records() -> list[HandRecord]:
    config = SimulationConfig(
        seats=tuple(
            SeatSpec(bot) for bot in ("nit", "tag", "lag", "station", "maniac", "basic")
        ),
        hands=150,
        seed=31,
        batch_size=150,
        record_history=True,
        stack_policy=StackPolicy.AUTO_REBUY,
    )

    return [HandRecord.from_dict(h) for h in run_simulation(config).totals.histories]


@pytest.mark.parametrize("writer", [pokerstars_text, winamax_text])
@pytest.mark.parametrize("money", [False, True])
def test_every_hand_written_by_a_site_reads_back_the_same(
    tmp_path: Path, writer, money: bool
) -> None:
    records = simulated_records()
    text = "\n\n".join(
        writer(record, "Calling Station", number, money=money)
        for number, record in enumerate(records, 1)
    )

    session = read_hand_history_file(write(tmp_path, text))

    assert session.notes == ()
    assert len(session.hands) == len(records)
    assert session.mode == (GameMode.CASH if money else GameMode.TOURNAMENT)

    for original, imported in zip(records, session.hands, strict=True):
        assert [(e.player, e.action, e.amount) for e in imported.actions] == [
            (e.player, e.action, e.amount) for e in original.actions
        ] or [(e.player, e.amount) for e in imported.actions] == [
            (e.player, e.amount) for e in original.actions
        ]
        assert dict(imported.payouts) == dict(original.payouts)
        assert imported.board == original.board
        assert imported.hole_cards("Calling Station") == original.hole_cards(
            "Calling Station"
        )
        shown = set(original.showdown) | {"Calling Station"}
        assert imported.hidden == set(original.players) - shown
