from tests.helpers import make_player, make_session


def test_dealer_moves_to_next_player() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    # Alice = BTN
    session.table.dealer_index = 0

    session.table.move_dealer()

    assert session.table.dealer_index == 1
    assert session.table.dealer is bob


def test_dealer_moves_clockwise_across_multiple_hands() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    # Alice = BTN
    session.table.dealer_index = 0

    session.table.move_dealer()
    assert session.table.dealer is bob

    session.table.move_dealer()
    assert session.table.dealer is charlie

    session.table.move_dealer()
    assert session.table.dealer is alice


def test_dealer_skips_busted_player() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    # Alice = BTN
    session.table.dealer_index = 0

    session.table.move_dealer()

    assert session.table.dealer_index == 2
    assert session.table.dealer is charlie


def test_dealer_skips_multiple_busted_players() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)
    dave = make_player("Dave")

    session = make_session(
        alice,
        bob,
        charlie,
        dave,
    )

    # Alice = BTN
    session.table.dealer_index = 0

    session.table.move_dealer()

    assert session.table.dealer_index == 3
    assert session.table.dealer is dave


def test_dealer_does_not_move_when_only_one_player_has_chips() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)

    session = make_session(
        alice,
        bob,
        charlie,
    )

    # Alice = BTN
    session.table.dealer_index = 0

    session.table.move_dealer()

    assert session.table.dealer_index == 0
    assert session.table.dealer is alice
