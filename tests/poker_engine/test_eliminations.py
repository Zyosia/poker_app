from tests.helpers import make_player, make_session


def test_player_with_zero_chips_is_busted() -> None:
    player = make_player(
        "Alice",
        stack=0,
    )

    assert player.is_busted is True


def test_player_with_chips_is_not_busted() -> None:
    player = make_player(
        "Alice",
        stack=100,
    )

    assert player.is_busted is False


def test_busted_player_is_not_automatically_eliminated() -> None:
    player = make_player(
        "Alice",
        stack=0,
    )

    assert player.is_busted is True
    assert player.eliminated is False


def test_eliminated_player_is_excluded_from_players_with_chips() -> None:
    alice = make_player(
        "Alice",
        stack=0,
    )
    bob = make_player(
        "Bob",
        stack=100,
    )
    charlie = make_player(
        "Charlie",
        stack=100,
    )

    alice.eliminated = True

    session = make_session(
        alice,
        bob,
        charlie,
    )

    assert session.get_players_with_chips() == [
        bob,
        charlie,
    ]


def test_eliminated_player_does_not_count_for_session_continuation() -> None:
    alice = make_player(
        "Alice",
        stack=0,
    )
    bob = make_player(
        "Bob",
        stack=100,
    )
    charlie = make_player(
        "Charlie",
        stack=100,
    )

    alice.eliminated = True

    session = make_session(
        alice,
        bob,
        charlie,
    )

    assert session.can_continue() is True

    charlie.eliminated = True

    assert session.can_continue() is False
