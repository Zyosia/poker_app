"""Texts of the hand history."""

from backend.poker_engine.blinds import BlindLevel
from backend.poker_engine.hand import start_hand
from backend.poker_engine.session import GameConfig, create_session
from frontend.formatting import describe_action


def test_forced_bets_including_antes_are_described() -> None:
    session = create_session(
        player_names=["Alice", "Bob", "Charlie"], config=GameConfig()
    )
    session.table.dealer_index = 0
    session.set_blind_level(BlindLevel(5, 10, ante=2))

    hand = start_hand(session)

    assert [f"{event.player} {describe_action(event)}" for event in hand.actions] == [
        "Bob posts ante 2",
        "Charlie posts ante 2",
        "Alice posts ante 2",
        "Bob posts small blind 5",
        "Charlie posts big blind 10",
    ]
