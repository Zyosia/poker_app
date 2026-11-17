"""My stats: the human's stats from saved sessions, with the Bot Arena's
collectors."""

from dataclasses import asdict
from pathlib import Path

import pytest

from backend.application.game_modes import GameMode
from backend.application.hand_records import HandRecord, load_session_record
from backend.simulation.config import SeatSpec, SimulationConfig, StackPolicy
from backend.simulation.my_stats import YOU, compute_my_stats, feed_record
from backend.simulation.runner import run_simulation
from backend.simulation.stats import EngineLabStats, PlayerStats, StatsCollector
from tests.session_files import (
    HUMAN,
    cash_session,
    downgrade_to_version_3,
    tournament_session,
)


@pytest.mark.parametrize(
    "policy", [StackPolicy.RESET_EACH_HAND, StackPolicy.AUTO_REBUY]
)
def test_recorded_hands_give_the_same_stats_as_the_live_hands(
    policy: StackPolicy,
) -> None:
    config = SimulationConfig(
        seats=tuple(
            SeatSpec(bot) for bot in ("nit", "tag", "lag", "station", "maniac", "basic")
        ),
        hands=800,
        seed=21,
        batch_size=800,
        record_history=True,
        stack_policy=policy,
    )
    result = run_simulation(config)
    live = result.totals.players
    players = {name: PlayerStats(name=name, bot=live[name].bot) for name in live}
    engine = EngineLabStats()
    collector = StatsCollector(players, engine, chart=[], chart_stride=10**9)

    for history in result.totals.histories:
        feed_record(HandRecord.from_dict(history), collector)

    for name, stats in live.items():
        expected, rebuilt = asdict(stats), asdict(players[name])

        for counted_by_the_runner in ("rebuys", "finishes"):
            del expected[counted_by_the_runner], rebuilt[counted_by_the_runner]

        assert rebuilt == expected, name

    assert engine == result.totals.engine


def test_cash_results_come_from_every_hand(tmp_path: Path) -> None:
    session = load_session_record(cash_session(tmp_path / "a.dat", hands=15))

    dealt_in = sum(HUMAN in hand.players for hand in session.hands)

    stats = compute_my_stats([session])

    assert dealt_in > 5, "Hero played most hands (a bot plays for Hero)"
    assert stats.sessions == 1
    assert stats.hands == stats.tendencies.hands == stats.cash.hands == dealt_in
    assert stats.tendencies.name == YOU
    assert stats.cash.net_chips == session.net_chips
    assert stats.cash.bb_per_100 == pytest.approx(
        session.net_chips / 10 / dealt_in * 100
    )
    assert sum(line.hands for line in stats.positions.values()) == dealt_in
    assert sum(line.net_chips for line in stats.positions.values()) == (
        session.net_chips
    )


def test_stats_add_up_across_sessions_and_modes(tmp_path: Path) -> None:
    sessions = [
        load_session_record(cash_session(tmp_path / "a.dat", hands=10, seed=1)),
        load_session_record(cash_session(tmp_path / "b.dat", hands=12, seed=2)),
        load_session_record(tournament_session(tmp_path / "t.dat", seed=3)),
        load_session_record(tournament_session(tmp_path / "s.dat", spin=True)),
    ]

    every = compute_my_stats(sessions)
    cash = compute_my_stats(sessions, GameMode.CASH)
    tournaments = compute_my_stats(sessions, GameMode.TOURNAMENT)
    spins = compute_my_stats(sessions, GameMode.SPIN)

    assert every.sessions == 4
    assert every.hands == cash.hands + tournaments.hands + spins.hands
    assert cash.hands == cash.cash.hands == cash.tendencies.hands > 0
    assert tournaments.cash.hands == 0
    assert tournaments.tournaments.played == 1 and tournaments.spins.played == 0
    assert spins.spins.played == 1
    finish = sessions[2].finish
    assert finish is not None
    assert tournaments.tournaments.profit == finish.profit
    assert every.tendencies.vpip_hands == sum(
        stats.tendencies.vpip_hands for stats in (cash, tournaments, spins)
    )


def test_hands_saved_before_v1_1_still_count(tmp_path: Path) -> None:
    path = cash_session(tmp_path / "a.dat", hands=10)
    current = compute_my_stats([load_session_record(path)])
    downgrade_to_version_3(path)

    old = compute_my_stats([load_session_record(path)])

    assert old.replayable_hands == 0 and current.replayable_hands == 10
    assert old.cash == current.cash
    assert old.positions == current.positions
    assert old.tendencies.vpip == current.tendencies.vpip
    assert old.tendencies.pfr == current.tendencies.pfr
    assert old.tendencies.saw_flop == current.tendencies.saw_flop


def test_an_unfinished_tournament_is_counted_apart(tmp_path: Path) -> None:
    session = load_session_record(tournament_session(tmp_path / "t.dat"))
    unfinished = type(session)(**{**session.__dict__, "finish": None})

    stats = compute_my_stats([unfinished])

    assert stats.tournaments.unfinished == 1
    assert stats.tournaments.played == 0
    assert stats.tournaments.roi is None


def test_no_session_gives_empty_stats() -> None:
    stats = compute_my_stats([])

    assert stats.hands == 0
    assert stats.cash.bb_per_100 is None
    assert stats.tendencies.vpip is None
