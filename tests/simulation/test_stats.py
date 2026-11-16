"""Statistics formulas, checked on hand-crafted hands with known answers."""

import math
from dataclasses import replace

import pytest

from backend.application.controllers import PlayerController
from backend.poker_engine.constants import Position
from backend.poker_engine.deck import Deck
from backend.poker_engine.hand_evaluator import HandCategory
from backend.poker_engine.session import GameConfig
from backend.simulation.config import SeatSpec, SimulationConfig
from backend.simulation.result import SimulationTotals
from backend.simulation.runner import plan_batches, run_batch, run_simulation
from backend.simulation.stats import (
    EngineLabStats,
    PlayerStats,
    StatsCollector,
    downsample_chart,
)
from backend.simulation.table import ArenaTable
from tests.simulation.helpers import ScriptedBot, stacked_deck

Script = list[tuple[str, int | None]]


def play_scripted_hand(
    scripts: dict[str, Script], deck: Deck | None = None
) -> tuple[dict[str, PlayerStats], EngineLabStats, ArenaTable]:
    """Play one hand with the first player on the button."""
    names = list(scripts)
    players = {name: PlayerStats(name=name, bot="scripted") for name in names}
    engine = EngineLabStats()
    controllers: dict[str, PlayerController] = {
        name: ScriptedBot(script) for name, script in scripts.items()
    }
    table = ArenaTable(
        seat_names=names,
        controllers=controllers,
        game_config=GameConfig(starting_stack=1000, small_blind=5, big_blind=10),
        observers=[StatsCollector(players, engine, chart=[])],
    )
    table.session.table.dealer_index = 0

    hand = table.start_hand(deck or Deck())

    # Check the action order the scripts rely on.
    expected_first = names[0] if len(names) in (2, 3) else names[3 % len(names)]
    assert hand.first_to_act is not None
    assert hand.first_to_act.name == expected_first

    while not hand.finished:
        table.step()

    return players, engine, table


def test_preflop_raise_three_bet_and_continuation_bet() -> None:
    # Alice on the button opens, Bob (small blind) 3-bets, Charlie (big
    # blind) folds, Alice calls; Bob c-bets the flop and Alice folds.
    players, engine, _ = play_scripted_hand(
        {
            "Alice": [("raise", 30), ("call", None), ("fold", None)],
            "Bob": [("raise", 90), ("raise", 100)],
            "Charlie": [("fold", None)],
        }
    )
    alice, bob, charlie = players["Alice"], players["Bob"], players["Charlie"]

    assert (alice.vpip_hands, bob.vpip_hands, charlie.vpip_hands) == (1, 1, 0)
    assert (alice.pfr_hands, bob.pfr_hands, charlie.pfr_hands) == (1, 1, 0)
    assert (bob.three_bet_opportunities, bob.three_bets) == (1, 1)
    # Only facing a single raise counts as a 3-bet opportunity.
    assert alice.three_bet_opportunities == charlie.three_bet_opportunities == 0

    assert (alice.saw_flop, bob.saw_flop, charlie.saw_flop) == (1, 1, 0)
    assert (bob.cbet_opportunities, bob.cbets) == (1, 1)
    assert (alice.fold_to_cbet_opportunities, alice.folds_to_cbet) == (1, 1)
    assert bob.postflop_aggressive_actions == 1
    assert alice.postflop_folds == 1

    assert alice.actions["PREFLOP"]["raise"] == 1
    assert alice.actions["PREFLOP"]["call"] == 1
    assert bob.actions["FLOP"]["bet"] == 1
    assert charlie.actions["PREFLOP"]["fold"] == 1

    assert (alice.net_chips, bob.net_chips, charlie.net_chips) == (-90, 100, -10)
    assert alice.positions[Position.BTN].net_chips == -90
    assert charlie.positions[Position.BB].hands == 1
    assert engine.showdowns == 0
    assert alice.went_to_showdown == bob.went_to_showdown == 0


SHOWDOWN_SCRIPTS: dict[str, Script] = {
    # Heads-up: Alice is the button and small blind, she completes, then
    # everyone checks down. Post-flop Bob acts first.
    "Alice": [("call", None), ("check", None), ("check", None), ("check", None)],
    "Bob": [("check", None)] * 4,
}


def test_showdown_won_and_lost() -> None:
    deck = stacked_deck(
        # Bob, Alice, Bob, Alice, then burn, flop, burn, turn, burn, river.
        ["2C", "AS", "7D", "AH", "3S", "KD", "9C", "4H", "5S", "JD", "6S", "8C"]
    )

    players, engine, _ = play_scripted_hand(SHOWDOWN_SCRIPTS, deck)
    alice, bob = players["Alice"], players["Bob"]

    assert (alice.vpip_hands, bob.vpip_hands) == (1, 0)
    assert (alice.saw_flop, alice.went_to_showdown, alice.won_at_showdown) == (1, 1, 1)
    assert (bob.saw_flop, bob.went_to_showdown, bob.won_at_showdown) == (1, 1, 0)
    assert alice.wtsd == 1.0 and alice.wsd == 1.0 and bob.wsd == 0.0
    assert alice.postflop_checks == 3

    assert engine.showdowns == 1
    assert engine.showdown_categories[HandCategory.PAIR] == 1
    assert engine.showdown_categories[HandCategory.HIGH_CARD] == 1
    assert engine.side_pot_counts == {0: 1}
    assert engine.split_pot_hands == 0
    assert engine.runout_hands == 0


def test_split_pot_counts_as_money_won_by_both() -> None:
    deck = stacked_deck(
        ["2C", "2H", "3D", "3S", "4C", "TS", "JS", "QD", "5D", "KC", "6D", "AH"]
    )

    players, engine, _ = play_scripted_hand(SHOWDOWN_SCRIPTS, deck)

    assert engine.split_pot_hands == 1
    assert players["Alice"].won_at_showdown == players["Bob"].won_at_showdown == 1
    assert players["Alice"].net_chips == players["Bob"].net_chips == 0


def test_all_in_preflop_runs_the_board_out() -> None:
    players, engine, table = play_scripted_hand(
        {"Alice": [("all_in", None)], "Bob": [("call", None)]}
    )

    assert engine.all_in_hands == 1
    assert engine.runout_hands == 1
    assert engine.showdowns == 1
    assert players["Bob"].saw_flop == 1
    assert players["Alice"].actions["PREFLOP"]["all_in"] == 1
    assert players["Alice"].pfr_hands == 1
    assert sum(player.stack for player in table.players) == 2000


def test_win_rate_formulas() -> None:
    stats = PlayerStats(name="Alice", bot="basic")

    for net_chips in (10, -20, 30, 0):
        stats.record_hand(net_chips)

    # 20 chips = 2 big blinds over 4 hands.
    assert stats.bb_per_100(10) == pytest.approx(50.0)

    variance = (100 + 400 + 900 + 0 - 4 * 5**2) / 3
    deviation_in_bb = math.sqrt(variance) / 10
    assert stats.standard_deviation_per_hand(10) == pytest.approx(deviation_in_bb)
    assert stats.standard_deviation_per_100(10) == pytest.approx(deviation_in_bb * 10)

    margin = 1.96 * deviation_in_bb * 100 / math.sqrt(4)
    low, high = stats.confidence_interval_bb_per_100(10) or (0.0, 0.0)
    assert low == pytest.approx(50.0 - margin)
    assert high == pytest.approx(50.0 + margin)


def test_rates_are_none_until_something_is_counted() -> None:
    stats = PlayerStats(name="Alice", bot="basic")

    assert stats.bb_per_100(10) is None
    assert stats.confidence_interval_bb_per_100(10) is None
    assert stats.vpip is None
    assert stats.aggression_factor is None
    assert stats.win_rate is None


def test_aggression_and_elimination_formulas() -> None:
    stats = PlayerStats(
        name="Alice",
        bot="basic",
        postflop_aggressive_actions=6,
        postflop_calls=3,
        postflop_folds=1,
        finishes=[2, 1, 1],
    )

    assert stats.aggression_factor == pytest.approx(2.0)
    assert stats.aggression_frequency == pytest.approx(0.6)
    assert stats.win_rate == pytest.approx(0.5)
    assert stats.average_finish == pytest.approx((2 * 1 + 1 * 2 + 1 * 3) / 4)


def test_merging_partial_results_equals_one_run() -> None:
    config = SimulationConfig(
        seats=(SeatSpec("tag"), SeatSpec("maniac"), SeatSpec("station")),
        hands=600,
        batch_size=200,
        seed=3,
    )
    full_run = run_simulation(config).totals

    merged = SimulationTotals.empty(config)

    for batch in plan_batches(config):
        merged.merge(run_batch(config, batch))

    assert merged.players == full_run.players
    assert merged.engine == full_run.engine
    assert merged.chart == full_run.chart
    assert merged.hands == full_run.hands == 600


def test_the_chart_follows_the_cumulative_results() -> None:
    config = SimulationConfig(
        seats=(SeatSpec("tag"), SeatSpec("maniac")), hands=5000, seed=4, workers=1
    )
    result = run_simulation(config)
    chart = result.chart

    assert chart[0] == (0, (0, 0))
    assert chart[-1] == (
        5000,
        (result.players["TAG"].net_chips, result.players["Maniac"].net_chips),
    )
    assert len(chart) <= 300
    hands = [point[0] for point in chart]
    assert hands == sorted(set(hands))


def test_the_chart_does_not_depend_on_the_batch_size_split_across_workers() -> None:
    config = SimulationConfig(
        seats=(SeatSpec("tag"), SeatSpec("maniac")), hands=1000, batch_size=250, seed=4
    )

    assert (
        run_simulation(config).chart == run_simulation(replace(config, workers=2)).chart
    )


def test_downsampling_keeps_the_first_and_last_points() -> None:
    points = [(index, (index,)) for index in range(1000)]

    sampled = downsample_chart(points, 300)

    assert len(sampled) == 300
    assert sampled[0] == points[0]
    assert sampled[-1] == points[-1]
    assert downsample_chart(points[:10], 300) == points[:10]
