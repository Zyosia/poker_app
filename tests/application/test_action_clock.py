"""The action clock and time bank, driven by a fake time source."""

import pytest

from backend.application.action_clock import (
    CLOCK_PRESETS,
    OFF,
    ActionClock,
    ClockPreset,
    clock_preset,
    record_timeout,
    timeout_action,
    tournament_clock,
)
from backend.application.controllers import (
    DecisionContext,
    HumanController,
    PlayerController,
)
from backend.application.game import PokerGame
from backend.application.persistence import serialize_session
from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.constants import ActionType
from backend.poker_engine.session import GameConfig, create_session

STANDARD = next(preset for preset in CLOCK_PRESETS if preset.name == "Standard")


class FakeTime:
    """A clock that only moves when the test says so."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def fake_time() -> FakeTime:
    return FakeTime()


def test_the_presets_match_the_documented_table() -> None:
    assert [
        (p.name, p.time_to_act, p.time_bank, p.top_up, p.max_time_bank)
        for p in CLOCK_PRESETS
    ] == [
        ("Relaxed", 30, 120, 10, 120),
        ("Standard", 20, 60, 10, 120),
        ("Fast", 15, 30, 5, 60),
        ("Hyper", 10, 20, 5, 40),
    ]
    assert all(p.top_up_every_hands == 25 for p in CLOCK_PRESETS)
    assert clock_preset(OFF) is None
    assert tournament_clock("Turbo") == "Fast"
    assert tournament_clock("Regular") == tournament_clock("Deep") == "Standard"

    with pytest.raises(ValueError):
        clock_preset("Glacial")


def test_the_time_bank_starts_when_the_time_to_act_runs_out(
    fake_time: FakeTime,
) -> None:
    clock = ActionClock(STANDARD, fake_time)
    clock.start_turn()

    fake_time.advance(19.5)
    assert clock.time_to_act_left() == pytest.approx(0.5)
    assert not clock.is_in_time_bank

    fake_time.advance(10.5)  # 30 s: 10 s into the time bank.
    assert clock.is_in_time_bank
    assert clock.time_to_act_left() == 0
    assert clock.time_bank_left() == pytest.approx(50)
    assert not clock.is_expired

    fake_time.advance(50)
    assert clock.is_expired


def test_the_time_bank_carries_over_and_unused_time_is_not_saved(
    fake_time: FakeTime,
) -> None:
    clock = ActionClock(STANDARD, fake_time)

    clock.start_turn()
    fake_time.advance(35)  # 15 s of time bank used.
    clock.end_turn()
    assert clock.time_bank == pytest.approx(45)

    clock.on_hand_finished()  # A new hand: no reset.
    clock.start_turn()
    fake_time.advance(5)  # 15 s of time to act left unused.
    clock.end_turn()

    assert clock.time_bank == pytest.approx(45)


def test_top_ups_follow_the_preset_up_to_its_maximum(fake_time: FakeTime) -> None:
    clock = ActionClock(STANDARD, fake_time)

    for _ in range(24):
        clock.on_hand_finished()

    assert clock.time_bank == 60

    clock.on_hand_finished()  # 25 hands: +10 s.
    assert clock.time_bank == 70

    for _ in range(25 * 10):
        clock.on_hand_finished()

    assert clock.time_bank == 120, "never above the maximum"


def test_a_spent_time_bank_is_topped_up_too(fake_time: FakeTime) -> None:
    preset = ClockPreset(
        "Test", 10, 20, top_up=5, top_up_every_hands=2, max_time_bank=40
    )
    clock = ActionClock(preset, fake_time)
    clock.start_turn()
    fake_time.advance(30)
    assert clock.is_expired
    clock.end_turn()
    assert clock.time_bank == 0

    clock.on_hand_finished()
    clock.on_hand_finished()

    assert clock.time_bank == 5


def test_pause_freezes_both_and_resumes_exactly(fake_time: FakeTime) -> None:
    clock = ActionClock(STANDARD, fake_time)
    clock.start_turn()
    fake_time.advance(12)

    clock.pause()
    fake_time.advance(600)
    assert clock.time_to_act_left() == pytest.approx(8)
    assert not clock.is_expired

    clock.resume()
    assert clock.time_to_act_left() == pytest.approx(8)

    fake_time.advance(18)  # 10 s into the time bank.
    clock.pause()
    fake_time.advance(600)
    assert clock.time_bank_left() == pytest.approx(50)
    clock.resume()
    fake_time.advance(50)

    assert clock.is_expired


def test_a_timeout_checks_when_free_and_folds_facing_a_bet() -> None:
    fold = LegalAction(type=ActionType.FOLD)
    check = LegalAction(type=ActionType.CHECK)
    call = LegalAction(type=ActionType.CALL, amount=20)

    assert timeout_action((fold, check)) == Action(type=ActionType.CHECK)
    assert timeout_action((fold, call)) == Action(type=ActionType.FOLD)


def test_the_history_records_the_reveal_and_the_timeouts() -> None:
    session = create_session(
        ["Hero", "Bot", "Other"],
        GameConfig(starting_stack=500, rebuy_stack=500, small_blind=5, big_blind=10),
    )
    session.table.dealer_index = 0  # Hero: Button, first to act pre-flop.
    hero = HumanController()

    class Script(PlayerController):
        def __init__(self, *actions: ActionType) -> None:
            self.actions = list(actions)

        def choose_action(self, context: DecisionContext) -> Action:
            return Action(type=self.actions.pop(0))

    game = PokerGame(
        session,
        {
            "Hero": hero,
            "Bot": Script(ActionType.ALL_IN),
            "Other": Script(ActionType.CALL),
        },
    )
    hand = game.start_hand()
    assert hand.first_to_act is not None and hand.first_to_act.name == "Hero"

    # Hero's clock runs out facing the big blind: a timeout folds.
    hero.submit(timeout_action(game.build_context(hand.first_to_act).legal_actions))
    event = game.step()
    assert event is not None and event.action == ActionType.FOLD
    record_timeout(hand, event)

    game.step()  # Bot (small blind) shoves.
    game.step()  # Other (big blind) calls: no more betting is possible.

    while not hand.finished:
        game.step()

    data = serialize_session(session)["hands"][0]

    assert data["timed_out_actions"] == [3]
    assert data["actions"][2]["player"] == "Hero"
    assert data["actions"][2]["action"] == ActionType.FOLD
    assert data["revealed_after_action"] == 5
    assert data["actions"][4]["player"] == "Other"
