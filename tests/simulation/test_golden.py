"""Golden fingerprints of seeded simulations.

They pin the exact results of the simulator before any optimization. A
change to the engine, the bots or the statistics that alters a single action,
card, payout or statistic changes a fingerprint. Never update the expected
values to make an optimization pass: an optimization must not change results.

Fields added to the exports after Beta 1.1 (``ADDED_HISTORY_FIELDS``) are
left out of the result fingerprint: they add information without changing
any result, and the fingerprint keeps pinning the same hands.
"""

import hashlib
import json
from collections.abc import Mapping

import pytest

from backend.poker_engine.models import Hand
from backend.simulation.config import SeatSpec, SimulationConfig, StackPolicy
from backend.simulation.events import HandObserver
from backend.simulation.result import SimulationResult
from backend.simulation.runner import run_simulation
from tests.simulation.helpers import AttachObserver

TIMING_FIELDS = ("duration_seconds", "hands_per_second")

ADDED_HISTORY_FIELDS = (
    "blind_level",
    "dead_money",
    "revealed_after_action",
    "timed_out_actions",
    "seats",
)
"""Hand history fields added in V1.0 (session file format version 2),
V1.0.1 (format version 3) and V1.1 (format version 4)."""


class HandFingerprint(HandObserver):
    """Hashes every finished hand: cards, actions, pots and payouts."""

    def __init__(self) -> None:
        self.digest = hashlib.sha256()
        self.hands = 0

    def on_hand_end(self, hand: Hand, stacks_before: Mapping[str, int]) -> None:
        self.hands += 1
        record = (
            sorted(stacks_before.items()),
            [(player.name, tuple(player.hand)) for player in hand.table.players],
            tuple(hand.community_cards),
            [
                (
                    event.street,
                    event.player,
                    event.action,
                    event.amount,
                    event.pot_after,
                )
                for event in hand.actions
            ],
            [(pot.amount, pot.winners) for pot in hand.pot_results],
            sorted(hand.payouts.items()),
            [(player.name, player.stack) for player in hand.table.players],
        )
        self.digest.update(repr(record).encode())


def result_fingerprint(result: SimulationResult) -> str:
    """Hash of every exported result except the timings."""
    data = result.to_dict()

    for name in TIMING_FIELDS:
        data.pop(name)

    for history in data["histories"]:
        for name in ADDED_HISTORY_FIELDS:
            history.pop(name)

    encoded = json.dumps(data, sort_keys=True, default=str).encode()

    return hashlib.sha256(encoded).hexdigest()[:16]


def seats(*bots: str) -> tuple[SeatSpec, ...]:
    return tuple(SeatSpec(bot) for bot in bots)


STYLES = ("nit", "tag", "lag", "station", "maniac", "basic")

GOLDEN_CONFIGS: dict[str, SimulationConfig] = {
    "6_basic": SimulationConfig(
        seats=seats(*("basic",) * 6), hands=1500, seed=11, batch_size=500
    ),
    "6_styles": SimulationConfig(
        seats=seats(*STYLES), hands=1500, seed=12, batch_size=500, record_history=True
    ),
    "heads_up": SimulationConfig(
        seats=seats("tag", "station"), hands=2000, seed=13, batch_size=500
    ),
    "duplicate": SimulationConfig(
        seats=seats("tag", "lag", "maniac"), hands=900, seed=14, duplicate=True
    ),
    "auto_rebuy": SimulationConfig(
        seats=seats(*STYLES),
        hands=1500,
        seed=15,
        batch_size=500,
        stack_policy=StackPolicy.AUTO_REBUY,
    ),
    "elimination": SimulationConfig(
        seats=seats("nit", "lag", "maniac"),
        sessions=6,
        sessions_per_batch=3,
        seed=16,
        stack_policy=StackPolicy.ELIMINATION,
    ),
}

# (hands played, per-hand fingerprint, result fingerprint)
GOLDEN_FINGERPRINTS: dict[str, tuple[int, str, str]] = {
    "6_basic": (1500, "0b5b1b2f774b514a", "79dfa67bddcca8ba"),
    "6_styles": (1500, "ad5f90c3525f39a7", "5e0ae20c4ca03085"),
    "heads_up": (2000, "c33790e72c147d24", "56fff24e429913ce"),
    "duplicate": (900, "a71eeb03bb8b2f2c", "a519c41c2b1c30e0"),
    "auto_rebuy": (1500, "d03c582603cd69e9", "585215ea26e3fcd6"),
    "elimination": (1116, "c8664b255df95382", "99f4de18b58b11a3"),
}


def fingerprint(
    config: SimulationConfig, attach_observer: AttachObserver
) -> tuple[int, str, str]:
    observer = HandFingerprint()
    attach_observer(observer)
    result = run_simulation(config)

    return (
        observer.hands,
        observer.digest.hexdigest()[:16],
        result_fingerprint(result),
    )


@pytest.mark.parametrize("name", list(GOLDEN_CONFIGS))
def test_simulation_matches_its_golden_fingerprint(
    name: str, attach_observer: AttachObserver
) -> None:
    assert (
        fingerprint(GOLDEN_CONFIGS[name], attach_observer)
        == (GOLDEN_FINGERPRINTS[name])
    )
