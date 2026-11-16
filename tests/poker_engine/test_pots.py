from backend.poker_engine.pots import build_pots, total_pot_amount
from tests.helpers import make_player


def test_build_single_main_pot() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)

    alice.total_contribution = 100
    bob.total_contribution = 100
    charlie.total_contribution = 100

    pots = build_pots(
        players=[alice, bob, charlie],
    )

    assert len(pots) == 1

    pot = pots[0]

    assert pot.amount == 300
    assert pot.contributors == (alice, bob, charlie)
    assert pot.eligible_players == (alice, bob, charlie)


def test_build_main_pot_and_one_side_pot() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)

    alice.total_contribution = 50
    bob.total_contribution = 100
    charlie.total_contribution = 100

    pots = build_pots(
        players=[alice, bob, charlie],
    )

    assert len(pots) == 2

    main_pot, side_pot = pots

    assert main_pot.amount == 150
    assert main_pot.contributors == (alice, bob, charlie)
    assert main_pot.eligible_players == (alice, bob, charlie)

    assert side_pot.amount == 100
    assert side_pot.contributors == (bob, charlie)
    assert side_pot.eligible_players == (bob, charlie)


def test_build_multiple_side_pots() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)

    alice.total_contribution = 50
    bob.total_contribution = 100
    charlie.total_contribution = 150

    pots = build_pots(
        players=[alice, bob, charlie],
    )

    assert len(pots) == 3

    main_pot, first_side_pot, second_side_pot = pots

    assert main_pot.amount == 150
    assert main_pot.contributors == (alice, bob, charlie)

    assert first_side_pot.amount == 100
    assert first_side_pot.contributors == (bob, charlie)

    assert second_side_pot.amount == 50
    assert second_side_pot.contributors == (charlie,)

    assert total_pot_amount(pots) == 300


def test_folded_player_contributes_but_is_not_eligible() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)

    alice.total_contribution = 100
    bob.total_contribution = 100
    charlie.total_contribution = 100

    bob.folded = True

    pots = build_pots(
        players=[alice, bob, charlie],
    )

    assert len(pots) == 1

    pot = pots[0]

    assert pot.amount == 300
    assert pot.contributors == (alice, bob, charlie)
    assert pot.eligible_players == (alice, charlie)


def test_zero_contribution_players_are_ignored() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=100)

    alice.total_contribution = 100
    bob.total_contribution = 100
    charlie.total_contribution = 0

    pots = build_pots(
        players=[alice, bob, charlie],
    )

    assert len(pots) == 1

    pot = pots[0]

    assert pot.amount == 200
    assert pot.contributors == (alice, bob)
    assert pot.eligible_players == (alice, bob)


def test_total_pot_amount_matches_all_contributions() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)

    alice.total_contribution = 75
    bob.total_contribution = 125
    charlie.total_contribution = 200

    pots = build_pots(
        players=[alice, bob, charlie],
    )

    assert total_pot_amount(pots) == 400
    assert sum(
        player.total_contribution for player in [alice, bob, charlie]
    ) == total_pot_amount(pots)
