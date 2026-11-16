"""Blind levels and structures: validation, level changes, last level."""

import pytest

from backend.poker_engine.actions import Action
from backend.poker_engine.blinds import AnteType, BlindLevel, BlindStructure
from backend.poker_engine.constants import ActionType
from backend.poker_engine.hand import play_hand, start_hand
from backend.poker_engine.session import GameConfig, create_session

LEVELS = (
    BlindLevel(5, 10),
    BlindLevel(10, 20),
    BlindLevel(20, 40, ante=40, ante_type=AnteType.BIG_BLIND),
)
STRUCTURE = BlindStructure(
    name="Test", levels=LEVELS, hands_per_level=2, minutes_per_level=1
)


@pytest.mark.parametrize(
    ("small_blind", "big_blind", "ante"), [(0, 10, 0), (10, 10, 0), (5, 10, -1)]
)
def test_invalid_levels_are_rejected(
    small_blind: int, big_blind: int, ante: int
) -> None:
    with pytest.raises(ValueError):
        BlindLevel(small_blind, big_blind, ante=ante)


def test_invalid_structures_are_rejected() -> None:
    with pytest.raises(ValueError):
        BlindStructure(name="Empty", levels=())

    with pytest.raises(ValueError):
        BlindStructure(name="Zero", levels=LEVELS, hands_per_level=0)


def test_the_level_changes_exactly_between_two_hands() -> None:
    # Two hands per level: hands 0-1 at level 0, hands 2-3 at level 1.
    assert [STRUCTURE.level_index_for_hand(hands) for hands in range(5)] == [
        0,
        0,
        1,
        1,
        2,
    ]
    assert STRUCTURE.hands_until_next_level(0) == 2
    assert STRUCTURE.hands_until_next_level(1) == 1
    assert STRUCTURE.hands_until_next_level(2) == 2


def test_play_stays_on_the_last_level() -> None:
    assert STRUCTURE.level_index_for_hand(1000) == 2
    assert STRUCTURE.level(99) == LEVELS[-1]
    assert STRUCTURE.hands_until_next_level(4) is None
    assert STRUCTURE.hands_until_next_level(1000) is None


def test_levels_by_time_use_the_elapsed_time_given() -> None:
    assert STRUCTURE.level_index_for_time(0) == 0
    assert STRUCTURE.level_index_for_time(59.9) == 0
    assert STRUCTURE.level_index_for_time(60) == 1
    assert STRUCTURE.level_index_for_time(10_000) == 2
    assert STRUCTURE.seconds_until_next_level(45) == pytest.approx(15)
    assert STRUCTURE.seconds_until_next_level(130) is None


def test_dead_money_and_description() -> None:
    assert BlindLevel(5, 10, ante=2).dead_money(players_dealt_in=6) == 12
    assert LEVELS[2].dead_money(players_dealt_in=6) == 40
    assert LEVELS[0].describe() == "5/10"
    assert BlindLevel(5, 10, ante=2).describe() == "5/10, ante 2"
    assert LEVELS[2].describe() == "20/40, ante 40 (big blind)"


def test_hands_follow_the_session_level_set_between_hands() -> None:
    session = create_session(
        player_names=["Alice", "Bob", "Charlie"], config=GameConfig()
    )
    session.table.dealer_index = 0
    fold_everything = lambda hand, player: Action(type=ActionType.FOLD)  # noqa: E731
    levels_played = []

    for hands_played in range(5):
        session.set_blind_level(
            STRUCTURE.level(STRUCTURE.level_index_for_hand(hands_played))
        )
        hand = play_hand(session, fold_everything)
        levels_played.append(hand.blind_level)
        session.table.move_dealer()

    assert levels_played == [LEVELS[0], LEVELS[0], LEVELS[1], LEVELS[1], LEVELS[2]]
    assert session.hands[2].min_bet == 20
    assert session.hands[4].dead_money == 40


def test_the_level_cannot_change_during_a_hand() -> None:
    session = create_session(player_names=["Alice", "Bob"], config=GameConfig())
    session.table.dealer_index = 0
    start_hand(session)

    with pytest.raises(RuntimeError):
        session.set_blind_level(LEVELS[1])


def test_a_new_session_plays_the_blinds_of_its_configuration() -> None:
    session = create_session(
        player_names=["Alice", "Bob"],
        config=GameConfig(small_blind=25, big_blind=50),
    )

    assert session.blind_level == BlindLevel(25, 50)
