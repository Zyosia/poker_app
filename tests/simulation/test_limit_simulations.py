"""Every bot style plays Pot Limit, Fixed Limit and a capped No Limit (V3.1.1).

The engine refuses any illegal action, and the runner checks the chips after
every hand: a run that completes is a run of legal hands.
"""

import pytest

from backend.bots.factory import BOT_TYPES
from backend.poker_engine.constants import BettingRules, BettingStructure
from backend.simulation.config import SeatSpec, SimulationConfig
from backend.simulation.runner import run_simulation
from backend.simulation.tournament_runner import (
    RunType,
    TournamentRunConfig,
    run_tournaments,
)

STYLES = tuple(BOT_TYPES)
SMALL_BET = 10
RULES = [
    BettingRules(BettingStructure.POT_LIMIT),
    BettingRules(BettingStructure.FIXED_LIMIT),
    BettingRules(BettingStructure.NO_LIMIT, cap=3),
]


def seats(styles: tuple[str, ...]) -> tuple[SeatSpec, ...]:
    return tuple(SeatSpec(style) for style in styles)


@pytest.mark.parametrize("rules", RULES, ids=lambda rules: str(rules.structure))
def test_every_style_plays_legal_hands(rules: BettingRules) -> None:
    for start in range(0, len(STYLES), 6):
        table = STYLES[start : start + 6]

        if len(table) < 2:
            table = (*table, "tag")

        config = SimulationConfig(
            seats=seats(table), hands=150, batch_size=150, seed=5, betting=rules
        )
        result = run_simulation(config)

        assert result.totals.hands == 150


def test_the_runs_record_and_export_their_betting() -> None:
    config = SimulationConfig(
        seats=seats(("tag", "lag", "station")),
        hands=200,
        batch_size=200,
        seed=6,
        record_history=True,
        betting=BettingRules(BettingStructure.FIXED_LIMIT),
    )
    data = run_simulation(config).to_dict()

    assert data["config"]["betting"] == {"structure": "fixed_limit", "cap": None}
    assert data["histories"]
    raises = 0

    for history in data["histories"]:
        assert history["betting"] == {"structure": "fixed_limit", "cap": 4}

        for event in history["actions"]:
            if event["action"] != "raise":
                continue

            big_street = event["street"] in ("TURN", "RIVER")
            bet = SMALL_BET * (2 if big_street else 1)
            assert event["bet_after"] % bet == 0
            assert event["bet_after"] <= 4 * bet  # The cap of four bets.
            raises += 1

    assert raises > 0


def test_no_limit_exports_stay_as_before() -> None:
    config = SimulationConfig(seats=seats(("tag", "lag")), hands=10, seed=1)

    assert "betting" not in run_simulation(config).to_dict()["config"]


@pytest.mark.parametrize("run_type", [RunType.TOURNAMENT, RunType.SPIN])
def test_limit_tournaments_pay_out_every_chip(run_type: RunType) -> None:
    config = TournamentRunConfig(
        seats=seats(("shark", "lag", "nit")),
        run_type=run_type,
        tournaments=4,
        tournaments_per_batch=4,
        seed=9,
        betting=BettingRules(BettingStructure.FIXED_LIMIT),
    )
    result = run_tournaments(config)

    assert result.totals.tournaments == 4
