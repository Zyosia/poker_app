from backend.game.pots import build_pots, total_pot_amount
from tests.game.conftest import make_player


def test_short_stack_player_can_only_contribute_to_main_pot() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)

    alice.total_contribution = 50
    bob.total_contribution = 100
    charlie.total_contribution = 100

    pots = build_pots(
        players=[alice, bob, charlie],
    )

    main_pot, side_pot = pots

    assert main_pot.amount == 150
    assert main_pot.eligible_players == (alice, bob, charlie)

    assert side_pot.amount == 100
    assert side_pot.eligible_players == (bob, charlie)


def test_short_stack_player_cannot_be_eligible_for_higher_side_pot() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)

    alice.total_contribution = 40
    bob.total_contribution = 100
    charlie.total_contribution = 150

    pots = build_pots(
        players=[alice, bob, charlie],
    )

    _, first_side_pot, second_side_pot = pots

    assert first_side_pot.eligible_players == (bob, charlie)
    assert second_side_pot.eligible_players == (charlie,)


def test_folded_player_remains_contributor_to_side_pot() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)

    alice.total_contribution = 50
    bob.total_contribution = 100
    charlie.total_contribution = 100

    bob.folded = True

    pots = build_pots(
        players=[alice, bob, charlie],
    )

    main_pot, side_pot = pots

    assert bob in main_pot.contributors
    assert bob not in main_pot.eligible_players

    assert bob in side_pot.contributors
    assert bob not in side_pot.eligible_players

    assert side_pot.eligible_players == (charlie,)


def test_all_side_pots_preserve_total_contribution() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)
    dave = make_player("Dave", stack=0)

    alice.total_contribution = 25
    bob.total_contribution = 75
    charlie.total_contribution = 125
    dave.total_contribution = 200

    players = [alice, bob, charlie, dave]

    pots = build_pots(players=players)

    assert total_pot_amount(pots) == 425
    assert sum(player.total_contribution for player in players) == 425


def test_side_pot_contains_only_players_who_reached_its_level() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)

    alice.total_contribution = 100
    bob.total_contribution = 200
    charlie.total_contribution = 300

    pots = build_pots(
        players=[alice, bob, charlie],
    )

    main_pot, first_side_pot, second_side_pot = pots

    assert main_pot.contributors == (alice, bob, charlie)
    assert first_side_pot.contributors == (bob, charlie)
    assert second_side_pot.contributors == (charlie,)
