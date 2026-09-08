from backend.game.models.models import Hand
from backend.game.models.session import GameConfig, create_session

# ============================================================
# Helpers
# ============================================================


def make_hand():
    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=1000,
            small_blind=5,
            big_blind=10,
        ),
    )

    session.table.dealer_index = 0

    hand = Hand(
        table=session.table,
    )

    hand.street = "PREFLOP"

    return session, hand


def make_session_with_hand():
    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=1000,
            small_blind=5,
            big_blind=10,
        ),
    )

    session.table.dealer_index = 0

    hand = Hand(
        table=session.table,
    )

    hand.street = "PREFLOP"

    return session, hand
