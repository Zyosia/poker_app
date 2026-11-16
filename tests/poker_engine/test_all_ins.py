from backend.poker_engine.constants import Street
from tests.helpers import (
    allowed_action_types,
    make_hand,
    make_player,
    make_session,
    play_betting_round,
)


def test_player_can_check_after_short_all_in_below_current_bet() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=8)
    charlie = make_player("Charlie", stack=500)

    session = make_session(
        alice,
        bob,
        charlie,
    )

    hand = make_hand(
        session,
        current_bet=10,
    )
    hand.street = Street.PREFLOP

    alice.current_bet = 10
    bob.current_bet = 8
    charlie.current_bet = 10

    actions = allowed_action_types(
        player=charlie,
        hand=hand,
    )

    assert "call" not in actions
    assert "check" in actions
    assert "raise" in actions
    assert "fold" in actions


def test_player_cannot_check_after_short_all_in_if_below_current_bet() -> None:
    bob = make_player("Bob", stack=8)
    charlie = make_player("Charlie", stack=500)

    session = make_session(
        bob,
        charlie,
    )

    hand = make_hand(
        session,
        current_bet=10,
    )
    hand.street = Street.PREFLOP

    bob.current_bet = 8
    charlie.current_bet = 5

    actions = allowed_action_types(
        player=charlie,
        hand=hand,
    )

    assert "check" not in actions
    assert "call" in actions
    assert "fold" in actions


def test_all_in_opening_bet_reopens_action() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=100)
    charlie = make_player("Charlie", stack=100)

    session = make_session(
        alice,
        bob,
        charlie,
    )

    hand = make_hand(
        session,
        current_bet=0,
    )
    hand.street = Street.FLOP

    alice.current_bet = 0
    bob.current_bet = 0
    charlie.current_bet = 0

    hand.last_raise_size = 25

    called_players, result = play_betting_round(
        hand,
        [
            ("all_in", None),
            ("call", None),
            ("call", None),
        ],
    )

    assert result is True

    assert called_players == [
        bob,
        charlie,
        alice,
    ]

    assert bob.all_in is True
    assert alice.all_in is False
    assert charlie.all_in is True
    assert hand.current_bet == 100
    assert hand.last_raiser is bob
    assert hand.last_raise_size == 100


def test_short_all_in_below_current_bet_does_not_change_current_bet() -> None:
    alice = make_player("Alice", stack=100)
    bob = make_player("Bob", stack=8)
    charlie = make_player("Charlie", stack=100)

    session = make_session(alice, bob, charlie)

    session.table.dealer_index = 0

    hand = make_hand(
        session,
        current_bet=10,
    )
    hand.street = Street.PREFLOP
    hand.first_to_act = alice

    alice.current_bet = 0
    bob.current_bet = 0
    charlie.current_bet = 10

    called_players, result = play_betting_round(
        hand,
        [
            ("call", None),
            ("all_in", None),
            ("check", None),
        ],
    )

    assert result is True

    assert bob.stack == 0
    assert bob.all_in is True
    assert bob.current_bet == 8

    assert hand.current_bet == 10

    assert called_players == [
        alice,
        bob,
        charlie,
    ]


def test_full_all_in_raise_reopens_action() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=100)
    charlie = make_player("Charlie", stack=500)

    session = make_session(alice, bob, charlie)

    hand = make_hand(
        session,
        current_bet=100,
    )
    hand.street = Street.FLOP
    hand.last_raise_size = 100

    alice.current_bet = 100
    bob.current_bet = 100
    charlie.current_bet = 100

    called_players, result = play_betting_round(
        hand,
        [
            ("all_in", None),
            ("call", None),
            ("call", None),
        ],
    )

    assert result is True

    assert bob.stack == 0
    assert bob.current_bet == 200
    assert bob.all_in is True

    assert hand.current_bet == 200
    assert hand.last_raiser is bob
    assert hand.last_raise_size == 100

    assert called_players == [
        bob,
        charlie,
        alice,
    ]


def test_all_in_exactly_matches_current_bet_is_not_a_raise() -> None:
    alice = make_player("Alice", stack=100)
    bob = make_player("Bob", stack=5)
    charlie = make_player("Charlie", stack=100)

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

    alice.current_bet = 10
    bob.current_bet = 5
    charlie.current_bet = 10

    called_players, result = play_betting_round(
        hand,
        [
            ("check", None),
            ("all_in", None),
            ("check", None),
        ],
    )

    assert result is True

    assert bob.stack == 0
    assert bob.current_bet == 10
    assert bob.all_in is True

    assert hand.current_bet == 10
    assert hand.last_raiser is None

    assert called_players == [
        alice,
        bob,
        charlie,
    ]


def test_short_all_in_above_current_bet_does_not_reopen_action() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=50)
    charlie = make_player("Charlie", stack=500)

    session = make_session(
        alice,
        bob,
        charlie,
    )

    session.table.dealer_index = 0

    hand = make_hand(
        session,
        current_bet=100,
    )
    hand.street = Street.FLOP
    hand.last_raise_size = 100

    alice.current_bet = 100
    bob.current_bet = 100
    charlie.current_bet = 100

    called_players, result = play_betting_round(
        hand,
        [
            ("all_in", None),
            ("call", None),
            ("call", None),
        ],
    )

    assert result is True

    assert bob.stack == 0
    assert bob.current_bet == 150
    assert bob.all_in is True

    # The short all-in becomes the bet to call...
    assert hand.current_bet == 150
    assert charlie.current_bet == 150
    assert alice.current_bet == 150

    # ...but Bob did not make a full raise.
    assert hand.last_raiser is None
    assert hand.last_raise_size == 100

    assert called_players == [
        bob,
        charlie,
        alice,
    ]


def test_full_all_in_raise_uses_last_raise_size() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=50)
    charlie = make_player("Charlie", stack=500)

    session = make_session(
        alice,
        bob,
        charlie,
    )

    session.table.dealer_index = 0

    hand = make_hand(
        session,
        current_bet=150,
    )
    hand.street = Street.FLOP
    hand.last_raise_size = 50

    bob.current_bet = 150
    charlie.current_bet = 150
    alice.current_bet = 150

    called_players, result = play_betting_round(
        hand,
        [
            ("all_in", None),
            ("call", None),
            ("call", None),
        ],
    )

    assert result is True

    assert bob.stack == 0
    assert bob.current_bet == 200
    assert bob.all_in is True

    assert hand.current_bet == 200
    assert hand.last_raise_size == 50
    assert hand.last_raiser is bob

    assert called_players == [
        bob,
        charlie,
        alice,
    ]


def test_short_all_in_does_not_allow_check_for_player_below_current_bet() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=50)
    charlie = make_player("Charlie", stack=500)

    session = make_session(
        alice,
        bob,
        charlie,
    )

    session.table.dealer_index = 0

    hand = make_hand(
        session,
        current_bet=100,
    )
    hand.street = Street.FLOP
    hand.last_raise_size = 100

    bob.current_bet = 100
    charlie.current_bet = 50
    alice.current_bet = 100

    called_players, result = play_betting_round(
        hand,
        [
            ("all_in", None),
            ("call", None),
            ("call", None),
        ],
    )

    assert result is True

    assert bob.stack == 0
    assert bob.current_bet == 150
    assert bob.all_in is True

    # The short all-in is the new bet to call, without being a full raise.
    assert hand.current_bet == 150
    assert hand.last_raiser is None

    assert charlie.current_bet == 150
    assert charlie.stack == 400

    assert alice.current_bet == 150

    assert called_players == [
        bob,
        charlie,
        alice,
    ]


def test_short_all_in_followed_by_folds_ends_hand_when_one_player_remains() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=50)
    charlie = make_player("Charlie", stack=500)

    session = make_session(
        alice,
        bob,
        charlie,
    )

    session.table.dealer_index = 0

    hand = make_hand(
        session,
        current_bet=100,
    )
    hand.street = Street.FLOP
    hand.last_raise_size = 100

    bob.current_bet = 100
    charlie.current_bet = 50
    alice.current_bet = 50

    called_players, result = play_betting_round(
        hand,
        [
            ("all_in", None),
            ("fold", None),
            ("fold", None),
        ],
    )

    assert result is False
    assert hand.finished is True

    assert bob.folded is False
    assert bob.all_in is True
    assert charlie.folded is True
    assert alice.folded is True

    assert hand.winner_by_fold is bob


def test_full_all_in_raise_reopens_players_who_already_acted() -> None:
    alice = make_player("Alice", stack=500)
    bob = make_player("Bob", stack=100)
    charlie = make_player("Charlie", stack=500)

    session = make_session(
        alice,
        bob,
        charlie,
    )

    session.table.dealer_index = 0

    hand = make_hand(
        session,
        current_bet=100,
    )
    hand.street = Street.FLOP
    hand.last_raise_size = 100

    bob.current_bet = 100
    charlie.current_bet = 100
    alice.current_bet = 100

    called_players, result = play_betting_round(
        hand,
        [
            ("check", None),  # Bob
            ("check", None),  # Charlie
            ("all_in", None),  # Alice: 100 -> 600
            ("call", None),  # Bob reopens
            ("call", None),  # Charlie reopens
        ],
    )

    assert result is True

    assert alice.stack == 0
    assert alice.current_bet == 600
    assert alice.all_in is True

    assert hand.current_bet == 600
    assert hand.last_raiser is alice
    assert hand.last_raise_size == 500

    assert called_players == [
        bob,
        charlie,
        alice,
        bob,
        charlie,
    ]
