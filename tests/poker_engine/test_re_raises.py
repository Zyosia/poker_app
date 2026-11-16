from backend.poker_engine.constants import Street
from tests.helpers import (
    make_hand,
    make_player,
    make_session,
    play_betting_round,
)


def test_raise_is_followed_by_player_immediately_to_left_of_raiser() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    session.table.dealer_index = 0

    hand = make_hand(
        session,
        current_bet=10,
    )
    hand.street = Street.PREFLOP
    hand.first_to_act = alice
    hand.last_raise_size = 10

    alice.current_bet = 10
    bob.current_bet = 10
    charlie.current_bet = 10

    called_players, result = play_betting_round(
        hand,
        [
            ("raise", 20),
            ("call", None),
            ("call", None),
        ],
    )

    assert result is True

    assert called_players == [
        alice,
        bob,
        charlie,
    ]


def test_re_raise_reopens_action_for_original_raiser() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    session.table.dealer_index = 0

    hand = make_hand(
        session,
        current_bet=10,
    )
    hand.street = Street.PREFLOP
    hand.first_to_act = alice
    hand.last_raise_size = 10

    alice.current_bet = 10
    bob.current_bet = 10
    charlie.current_bet = 10

    called_players, result = play_betting_round(
        hand,
        [
            # Alice raises to 20.
            ("raise", 20),
            # Bob re-raises to 30.
            ("raise", 30),
            # Charlie calls 30.
            ("call", None),
            # Alice must respond to Bob's re-raise.
            ("call", None),
        ],
    )

    assert result is True

    assert called_players == [
        alice,
        bob,
        charlie,
        alice,
    ]

    assert hand.current_bet == 30
    assert hand.last_raiser is bob
    assert hand.last_raise_size == 10

    assert alice.current_bet == 30
    assert bob.current_bet == 30
    assert charlie.current_bet == 30


def test_multiple_re_raises_follow_clockwise_action_order() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    session.table.dealer_index = 0

    hand = make_hand(
        session,
        current_bet=10,
    )
    hand.street = Street.PREFLOP
    hand.first_to_act = alice
    hand.last_raise_size = 10

    alice.current_bet = 10
    bob.current_bet = 10
    charlie.current_bet = 10

    called_players, result = play_betting_round(
        hand,
        [
            # Alice: 10 -> 20
            ("raise", 20),
            # Bob: 10 -> 30
            ("raise", 30),
            # Charlie: 10 -> 40
            ("raise", 40),
            # Alice: 20 -> 40
            ("call", None),
            # Bob: 30 -> 40
            ("call", None),
        ],
    )

    assert result is True

    assert called_players == [
        alice,
        bob,
        charlie,
        alice,
        bob,
    ]

    assert hand.current_bet == 40
    assert hand.last_raiser is charlie
    assert hand.last_raise_size == 10

    assert alice.current_bet == 40
    assert bob.current_bet == 40
    assert charlie.current_bet == 40


def test_re_raise_updates_last_raiser_and_last_raise_size() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    session.table.dealer_index = 0

    hand = make_hand(
        session,
        current_bet=20,
    )
    hand.street = Street.FLOP
    hand.last_raise_size = 20

    alice.current_bet = 20
    bob.current_bet = 20
    charlie.current_bet = 20

    called_players, result = play_betting_round(
        hand,
        [
            # Bob raises from 20 to 40.
            ("raise", 40),
            # Charlie re-raises from 20 to 60.
            ("raise", 60),
            # Alice calls to 60.
            ("call", None),
            # Bob calls to 60.
            ("call", None),
        ],
    )

    assert result is True

    assert called_players == [
        bob,
        charlie,
        alice,
        bob,
    ]

    assert hand.current_bet == 60
    assert hand.last_raiser is charlie
    assert hand.last_raise_size == 20

    assert alice.current_bet == 60
    assert bob.current_bet == 60
    assert charlie.current_bet == 60
