from backend.game.engine.hand import Hand
from backend.game.engine.pots import Pot
from backend.game.engine.showdown import split_pot
from tests.game.conftest import make_player, make_session


def make_hand(*players) -> Hand:
    session = make_session(*players)
    session.table.dealer_index = 0

    return Hand(
        table=session.table,
    )


def test_split_pot_evenly_between_two_winners() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)

    hand = make_hand(alice, bob)

    pot = Pot(
        amount=100,
        contributors=(alice, bob),
        eligible_players=(alice, bob),
    )

    payouts = split_pot(
        hand=hand,
        pot=pot,
        winners=[alice, bob],
    )

    assert payouts == {
        "Alice": 50,
        "Bob": 50,
    }


def test_split_pot_evenly_between_three_winners() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)

    hand = make_hand(alice, bob, charlie)

    pot = Pot(
        amount=99,
        contributors=(alice, bob, charlie),
        eligible_players=(alice, bob, charlie),
    )

    payouts = split_pot(
        hand=hand,
        pot=pot,
        winners=[alice, bob, charlie],
    )

    assert payouts == {
        "Alice": 33,
        "Bob": 33,
        "Charlie": 33,
    }


def test_odd_chip_goes_to_first_winner_left_of_dealer() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)

    hand = make_hand(alice, bob, charlie)

    pot = Pot(
        amount=101,
        contributors=(alice, bob, charlie),
        eligible_players=(alice, bob),
    )

    payouts = split_pot(
        hand=hand,
        pot=pot,
        winners=[alice, bob],
    )

    assert payouts == {
        "Alice": 50,
        "Bob": 51,
    }


def test_odd_chip_follows_clockwise_order_from_left_of_dealer() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)
    dave = make_player("Dave", stack=0)

    hand = make_hand(alice, bob, charlie, dave)

    pot = Pot(
        amount=100,
        contributors=(alice, bob, charlie, dave),
        eligible_players=(alice, charlie, dave),
    )

    payouts = split_pot(
        hand=hand,
        pot=pot,
        winners=[alice, charlie, dave],
    )

    assert payouts == {
        "Alice": 33,
        "Charlie": 34,
        "Dave": 33,
    }


def test_non_winner_does_not_receive_anything() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)

    hand = make_hand(alice, bob, charlie)

    pot = Pot(
        amount=100,
        contributors=(alice, bob, charlie),
        eligible_players=(alice, bob, charlie),
    )

    payouts = split_pot(
        hand=hand,
        pot=pot,
        winners=[alice, bob],
    )

    assert payouts == {
        "Alice": 50,
        "Bob": 50,
    }
    assert "Charlie" not in payouts
