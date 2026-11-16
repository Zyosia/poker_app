from __future__ import annotations

from collections.abc import Iterator

import pytest

from backend.poker_engine.actions import Action
from backend.poker_engine.hand import play_hand
from backend.poker_engine.models import Hand, Player
from backend.poker_engine.session import GameConfig, create_session
from tests.helpers import scripted_actions, to_action

RUNS = 100


@pytest.mark.parametrize("run", range(RUNS))
def test_hand_with_side_pot_reaches_showdown_stress_100_runs(
    run: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A complete hand with unequal stacks creates and distributes a side pot."""
    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=50,
            small_blind=5,
            big_blind=10,
        ),
    )

    # Give Bob and Charlie a larger stack so the hand can create a side pot.
    bob = session.players[1]
    bob.stack = 100
    charlie = session.players[2]
    charlie.stack = 200

    session.table.dealer_index = 0

    initial_total = sum(player.stack for player in session.players)

    choose_action = scripted_actions(
        [
            # PREFLOP.
            # Alice BTN -> all-in for 50.
            ("all_in", None),
            # Bob SB -> call Alice's 50.
            ("call", None),
            # Charlie BB -> call Alice's 50.
            ("call", None),
            # FLOP: Bob first.
            # Bob goes all-in for another 50.
            ("all_in", None),
            # Charlie matches the side-pot bet.
            ("call", None),
        ],
    )

    hand = play_hand(session, choose_action)
    alice, bob, charlie = session.players

    assert hand.finished is True
    assert len(hand.community_cards) == 5
    assert hand.pot == 0

    assert alice.total_contribution == 50
    assert bob.total_contribution == 100
    assert charlie.total_contribution == 100

    assert len(hand.pot_results) == 2

    pot_amounts = [pot_result.amount for pot_result in hand.pot_results]
    assert sorted(pot_amounts) == [100, 150]

    assert sum(player.stack for player in session.players) == initial_total
    assert sum(hand.payouts.values()) == 250

    assert alice.all_in is True

    # So in this simmulation the Main pot is 150,
    # Any player with the bet hand can win this pot.
    # The Side pot is 100 and only Bob or Charlie,
    # Depending on who has the best hand can win this pot.

    # When all three player splits (They all have the same hand strength)
    # here's what happen :
    # The main is splitted between the three player, so 150/3 -> Alice, Bob and Charlie get 50.
    # Then the side is splitted between Bob and Charlie, so 100/2 -> Bob and Charlie gets another 50.
    # So in the end the player are back to the stack they had before the hand. (As none of them won)

    # Alice started with 50 and contributed to 50, so she's all-in.
    # Also she is not in the SIDE pot so she cannot win it.
    # Her final stack is therefore either
    # 0 if she looses both the main.
    # 50 if the main split among the 3 players
    # 75 if she splits with either Bob or Charlie
    # 150 if she wins the main pot.

    assert alice.stack in {0, 50, 75, 150}

    # The final stacks of Bob and Charlie depend on whether they win the side and/or the main pot(s).

    # Bob started with 100 and contributed to 100, so he is all-in.
    # According to the other player contributions,
    # His final stack can be :
    # 0   if he looses both the main and side pots.
    # 50  if he looses the main and split the side (so Alice won the main).
    # 100 if he looses the main and win the side pots.
    # 100 if all the players split,
    # 125 if he splits the main and side pots with Charlie
    # 175 if he splits with Alice the main and win the side pots.
    # 250 if he wins the main pot and side pot.
    assert bob.stack in {0, 50, 100, 125, 175, 250}

    # Charlie started with 200 and contributed 100. So he has 100 chips left in his stack.
    # The outcomes are similare than Bob's one, but as he as still 100 more chips :
    # His final stack is therefore either :
    # 100 if he looses both main and side pots.
    # 150 if he looses the main and split the side pots (So Alice won the main).
    # 200 if he looses the main and win the side pots.
    # 200 if all the player splits.
    # 225 if he split the main and side pots with Bob
    # 275 if he splits with Alice and win the side pots.
    # 350 if he wins both the main and side pots.
    assert charlie.stack in {100, 150, 200, 225, 275, 350}


def assert_chip_integrity(session, initial_total: int) -> None:
    """Assert the fundamental chip invariants of a completed hand."""
    assert all(player.stack >= 0 for player in session.players)
    assert all(player.total_contribution >= 0 for player in session.players)
    assert sum(player.stack for player in session.players) == initial_total


@pytest.mark.parametrize("run", range(RUNS))
def test_complete_hand_stress_100_runs(
    run: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run a complete check-down hand and verify its invariants."""
    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=100,
            small_blind=5,
            big_blind=10,
        ),
    )

    session.table.dealer_index = 0

    initial_total = sum(player.stack for player in session.players)

    choose_action = scripted_actions(
        [
            # PREFLOP: Alice BTN, Bob SB, Charlie BB.
            ("call", None),
            ("call", None),
            ("check", None),
            # FLOP: Bob, Charlie, Alice.
            ("check", None),
            ("check", None),
            ("check", None),
            # TURN.
            ("check", None),
            ("check", None),
            ("check", None),
            # RIVER.
            ("check", None),
            ("check", None),
            ("check", None),
        ],
    )

    hand = play_hand(session, choose_action)

    assert hand.finished is True
    assert hand.street == "RIVER"
    assert len(hand.community_cards) == 5
    assert hand.pot == 0
    assert len(hand.showdown_evaluations) == 3
    assert len(hand.pot_results) == 1

    assert_chip_integrity(session, initial_total)
    assert sum(hand.payouts.values()) == 30


@pytest.mark.parametrize("run", range(RUNS))
def test_fold_hand_stress_100_runs(
    run: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeatedly resolve a hand by fold without reaching showdown."""
    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=100,
            small_blind=5,
            big_blind=10,
        ),
    )

    session.table.dealer_index = 0

    initial_total = sum(player.stack for player in session.players)

    choose_action = scripted_actions(
        [
            # PREFLOP: Alice raises, then both opponents fold.
            ("raise", 30),
            ("fold", None),
            ("fold", None),
        ],
    )

    hand = play_hand(session, choose_action)
    alice, bob, charlie = session.players

    assert hand.finished is True
    assert hand.winner_by_fold is alice
    assert hand.showdown_evaluations == {}
    assert hand.pot == 0
    assert hand.payouts == {"Alice": 45}

    assert alice.stack == 115
    assert bob.stack == 95
    assert charlie.stack == 90

    assert bob.folded is True
    assert charlie.folded is True

    assert_chip_integrity(session, initial_total)


@pytest.mark.parametrize("run", range(RUNS))
def test_all_in_auto_runout_stress_100_runs(
    run: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeatedly run an all-in hand through automatic board completion."""
    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=30,
            small_blind=5,
            big_blind=10,
        ),
    )

    session.table.dealer_index = 0

    initial_total = sum(player.stack for player in session.players)

    choose_action = scripted_actions(
        [
            # PREFLOP: all three players are all-in.
            ("all_in", None),
            ("all_in", None),
            ("all_in", None),
        ],
    )

    hand = play_hand(session, choose_action)

    assert hand.finished is True
    assert len(hand.community_cards) == 5
    assert hand.pot == 0
    assert all(player.all_in for player in session.players)
    assert len(hand.showdown_evaluations) == 3
    assert sum(hand.payouts.values()) == 90

    assert_chip_integrity(session, initial_total)


@pytest.mark.parametrize("run", range(RUNS))
def test_side_pot_stress_100_runs(
    run: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeatedly exercise main/side-pot creation and distribution."""
    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=50,
            small_blind=5,
            big_blind=10,
        ),
    )

    # Reachable stack configuration:
    # Alice starts with 50, Bob with 100, Charlie with 200.
    session.players[1].stack = 100
    session.players[2].stack = 200

    session.table.dealer_index = 0

    initial_total = sum(player.stack for player in session.players)

    choose_action = scripted_actions(
        [
            # PREFLOP:
            # Alice BTN -> all-in for 50.
            ("all_in", None),
            # Bob SB -> call 50.
            ("call", None),
            # Charlie BB -> call 50.
            ("call", None),
            # FLOP:
            # Bob -> all-in for 100 total.
            ("all_in", None),
            # Charlie -> call the additional 50.
            ("call", None),
        ],
    )

    hand = play_hand(session, choose_action)
    alice, bob, charlie = session.players

    assert hand.finished is True
    assert len(hand.community_cards) == 5
    assert hand.pot == 0

    assert alice.total_contribution == 50
    assert bob.total_contribution == 100
    assert charlie.total_contribution == 100

    assert len(hand.pot_results) == 2

    assert sorted(pot_result.amount for pot_result in hand.pot_results) == [100, 150]

    # The payouts must exactly match the money committed to the pots.
    assert sum(hand.payouts.values()) == 250

    # Alice is eligible only for the main pot.
    # Bob and Charlie are eligible for both pots.
    assert alice.stack in {0, 50, 75, 150}
    assert bob.stack in {0, 50, 100, 125, 175, 250}
    assert charlie.stack in {100, 150, 200, 225, 275, 350}

    assert_chip_integrity(session, initial_total)


@pytest.mark.parametrize("run", range(RUNS))
def test_multiple_hands_stress_100_runs(
    run: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Play multiple consecutive hands and preserve session invariants."""
    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=100,
            small_blind=5,
            big_blind=10,
        ),
    )

    session.table.dealer_index = 0

    initial_total = sum(player.stack for player in session.players)

    choose_action = scripted_actions(
        [
            # HAND #1: Alice is BTN.
            # Preflop: Alice, Bob, Charlie.
            ("call", None),
            ("call", None),
            ("check", None),
            # Flop / turn / river: Bob, Charlie, Alice.
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            # HAND #2: Bob is BTN.
            # Preflop: Charlie, Alice, Bob.
            ("call", None),
            ("call", None),
            ("check", None),
            # Flop / turn / river: Charlie, Alice, Bob.
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
            ("check", None),
        ],
    )

    hand_one = play_hand(session, choose_action)

    assert hand_one.finished is True
    assert session.hand_number == 1
    assert hand_one.pot == 0
    assert len(hand_one.community_cards) == 5
    assert sum(player.stack for player in session.players) == initial_total

    session.table.move_dealer()

    assert session.table.dealer is session.players[1]

    hand_two = play_hand(session, choose_action)

    assert hand_two.finished is True
    assert session.hand_number == 2
    assert hand_two.pot == 0
    assert len(hand_two.community_cards) == 5
    assert sum(player.stack for player in session.players) == initial_total


@pytest.mark.parametrize("run", range(RUNS))
def test_raise_reraise_stress_100_runs(
    run: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeatedly verify that a re-raise correctly reopens action."""
    session = create_session(
        player_names=["Alice", "Bob", "Charlie"],
        config=GameConfig(
            starting_stack=100,
            small_blind=5,
            big_blind=10,
        ),
    )

    session.table.dealer_index = 0

    initial_total = sum(player.stack for player in session.players)
    actions_seen: list[str] = []

    action_iterator: Iterator[tuple[str, int | None]] = iter(
        [
            # PREFLOP:
            # Alice BTN raises to 30.
            ("raise", 30),
            # Bob SB re-raises to 60.
            ("raise", 60),
            # Charlie BB calls 60.
            ("call", None),
            # Alice must act again after Bob's full raise.
            ("call", None),
            # FLOP.
            ("check", None),
            ("check", None),
            ("check", None),
            # TURN.
            ("check", None),
            ("check", None),
            ("check", None),
            # RIVER.
            ("check", None),
            ("check", None),
            ("check", None),
        ],
    )

    def choose_action(hand: Hand, player: Player) -> Action:
        actions_seen.append(player.name)
        return to_action(next(action_iterator))

    hand = play_hand(session, choose_action)

    assert hand.finished is True

    assert actions_seen[:4] == [
        "Alice",
        "Bob",
        "Charlie",
        "Alice",
    ]

    assert hand.pot == 0
    assert sum(player.stack for player in session.players) == initial_total
