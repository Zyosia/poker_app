"""The hand replayer: recorded hands dealt again through the engine."""

import random
from dataclasses import replace
from pathlib import Path

import pytest

from backend.application.hand_records import HandRecord, load_session_record
from backend.application.persistence import serialize_session
from backend.application.replay import HandReplay, ReplayError
from backend.poker_engine.constants import Street
from backend.simulation.config import SeatSpec, SimulationConfig, StackPolicy
from backend.simulation.runner import run_simulation
from backend.simulation.tournament_runner import (
    RunType,
    TournamentRunConfig,
    create_tournament,
)
from tests.session_files import HUMAN, cash_session, downgrade_to_version_3

STYLES = ("nit", "tag", "lag", "station", "maniac", "basic")


def simulated_records(hands: int, seed: int) -> list[HandRecord]:
    config = SimulationConfig(
        seats=tuple(SeatSpec(bot) for bot in STYLES),
        hands=hands,
        seed=seed,
        batch_size=hands,
        record_history=True,
        stack_policy=StackPolicy.AUTO_REBUY,
    )

    return [HandRecord.from_dict(h) for h in run_simulation(config).totals.histories]


def test_every_simulated_hand_replays_to_its_recorded_end() -> None:
    """All-ins, side pots, splits and folds: the engine plays them again."""
    for record in simulated_records(hands=400, seed=31):
        replay = HandReplay(record)
        end = replay.hand_at(replay.step_count)

        assert end.finished
        assert dict(end.payouts) == dict(record.payouts)
        assert tuple(end.community_cards) == record.board
        assert [(e.player, e.action, e.amount) for e in end.actions] == [
            (e.player, e.action, e.amount) for e in record.actions
        ]


@pytest.mark.parametrize("run_type", [RunType.TOURNAMENT, RunType.SPIN])
def test_tournament_hands_with_antes_replay(run_type: RunType) -> None:
    bots = ("tag", "lag", "maniac") if run_type == RunType.SPIN else STYLES
    config = TournamentRunConfig(
        seats=tuple(SeatSpec(bot) for bot in bots), run_type=run_type, seed=7
    )
    tournament = create_tournament(config, 0, keep_hands=True)
    tournament.play_to_end()
    hands = serialize_session(tournament.session)["hands"]
    records = [HandRecord.from_dict(hand) for hand in hands]

    assert any(record.blind_level.ante for record in records)

    for record in records:
        HandReplay(record)  # Raises if the replay differs.


def test_a_step_is_one_decision_or_one_street(tmp_path: Path) -> None:
    session = load_session_record(cash_session(tmp_path / "s.dat", hands=6))

    for record in session.hands:
        replay = HandReplay(record)
        start = replay.start()
        assert start.street == Street.PREFLOP and not start.finished
        assert all(e.action.startswith("post_") for e in start.actions)

        for step in range(replay.step_count):
            before = replay.hand_at(step)
            after = replay.hand_at(step + 1)
            new_actions = len(after.actions) - len(before.actions)
            new_streets = len(after.streets) - len(before.streets)

            assert (new_actions, new_streets) in ((1, 0), (0, 1), (0, 0))
            assert new_actions == 1 or before.current_player is None

        assert replay.hand_at(replay.step_count).finished


def test_the_human_sees_their_own_cards_in_the_replay(tmp_path: Path) -> None:
    record = load_session_record(cash_session(tmp_path / "s.dat", hands=3)).hands[2]
    hand = HandReplay(record).start()

    hero = next(player for player in hand.table.players if player.name == HUMAN)
    assert tuple(hero.hand) == record.hole_cards(HUMAN)


def test_a_replay_never_touches_the_global_rng(tmp_path: Path) -> None:
    record = load_session_record(cash_session(tmp_path / "s.dat", hands=1)).hands[0]
    random.seed(5)
    expected = random.random()
    random.seed(5)

    replay = HandReplay(record)
    replay.hand_at(replay.step_count)

    assert random.random() == expected


def test_hands_saved_before_v1_1_cannot_be_replayed(tmp_path: Path) -> None:
    path = cash_session(tmp_path / "s.dat", hands=2)
    downgrade_to_version_3(path)
    record = load_session_record(path).hands[0]

    with pytest.raises(ReplayError, match="saved before V1.1"):
        HandReplay(record)


def test_an_unfinished_hand_cannot_be_replayed(tmp_path: Path) -> None:
    record = load_session_record(cash_session(tmp_path / "s.dat", hands=1)).hands[0]

    with pytest.raises(ReplayError, match="not finished"):
        HandReplay(replace(record, finished=False))


def test_a_record_that_does_not_follow_the_rules_is_refused(tmp_path: Path) -> None:
    record = load_session_record(cash_session(tmp_path / "s.dat", hands=1)).hands[0]
    decision = next(
        i for i, e in enumerate(record.actions) if not e.action.startswith("post_")
    )
    actions = list(record.actions)
    actions[decision] = replace(actions[decision], player="Nobody")

    with pytest.raises(ReplayError, match="does not match"):
        HandReplay(replace(record, actions=tuple(actions)))


def test_a_record_with_other_payouts_is_refused(tmp_path: Path) -> None:
    record = load_session_record(cash_session(tmp_path / "s.dat", hands=1)).hands[0]
    payouts = {name: amount + 1 for name, amount in record.payouts.items()}

    with pytest.raises(ReplayError, match="does not end as recorded"):
        HandReplay(replace(record, payouts=payouts))


def test_a_record_with_a_card_twice_is_refused(tmp_path: Path) -> None:
    record = load_session_record(cash_session(tmp_path / "s.dat", hands=1)).hands[0]
    assert record.seats is not None
    first, second = record.seats[0], record.seats[1]
    seats = (replace(first, hole_cards=second.hole_cards), *record.seats[1:])

    with pytest.raises(ReplayError, match="cannot be dealt again"):
        HandReplay(replace(record, seats=seats))


def test_steps_outside_the_hand_are_refused(tmp_path: Path) -> None:
    record = load_session_record(cash_session(tmp_path / "s.dat", hands=1)).hands[0]
    replay = HandReplay(record)

    with pytest.raises(ValueError, match="outside"):
        replay.hand_at(replay.step_count + 1)

    with pytest.raises(ReplayError, match="over"):
        replay.advance(replay.hand_at(replay.step_count))
