from unittest.mock import patch

from backend.game.betting import (
    betting_round,
    betting_round_can_continue,
    count_remaining_players,
    finish_by_fold,
    get_allowed_actions,
    get_next_pending_player,
    get_players_in_betting_order,
    get_table_order,
)
from tests.game.conftest import make_hand, make_player, make_session

# ============================================================
# get_next_pending_player
# ============================================================


def test_get_next_pending_player_returns_player_from_start() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    players = [alice, bob, charlie]

    result = get_next_pending_player(
        players=players,
        pending_players={
            id(bob),
            id(charlie),
        },
        start_index=1,
    )

    assert result is bob


def test_get_next_pending_player_skips_non_pending_players() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    players = [alice, bob, charlie]

    result = get_next_pending_player(
        players=players,
        pending_players={
            id(charlie),
        },
        start_index=0,
    )

    assert result is charlie


def test_get_next_pending_player_wraps_around() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    players = [alice, bob, charlie]

    result = get_next_pending_player(
        players=players,
        pending_players={
            id(alice),
        },
        start_index=2,
    )

    assert result is alice


def test_get_next_pending_player_returns_none_when_empty() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")

    result = get_next_pending_player(
        players=[alice, bob],
        pending_players=set(),
        start_index=0,
    )

    assert result is None


def test_get_next_pending_player_returns_none_for_empty_players() -> None:
    result = get_next_pending_player(
        players=[],
        pending_players=set(),
        start_index=0,
    )

    assert result is None


# ============================================================
# Table order
# ============================================================


def test_get_table_order_starts_with_dealer() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    session.table.dealer_index = 1

    assert get_table_order(session) == [
        bob,
        charlie,
        alice,
    ]


def test_get_table_order_excludes_busted_players() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob", stack=0)
    bob.eliminated = True
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    session.table.dealer_index = 0

    assert get_table_order(session) == [
        alice,
        charlie,
    ]


def test_get_table_order_keeps_all_in_players() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob", stack=0)
    bob.all_in = True
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    assert get_table_order(session) == [
        alice,
        bob,
        charlie,
    ]


def test_postflop_order_starts_left_of_button() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    session = make_session(alice, bob, charlie)

    # Alice = BTN
    session.table.dealer_index = 0

    hand = make_hand(session)
    hand.street = "FLOP"

    players = get_players_in_betting_order(
        session=session,
        hand=hand,
    )

    assert players == [
        bob,
        charlie,
        alice,
    ]


def test_postflop_order_skips_folded_button() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    alice.folded = True

    session = make_session(alice, bob, charlie)

    # Alice = BTN
    session.table.dealer_index = 0

    hand = make_hand(session)
    hand.street = "FLOP"

    players = get_players_in_betting_order(
        session=session,
        hand=hand,
    )

    assert players == [
        bob,
        charlie,
    ]


def test_postflop_order_skips_all_in_player_left_of_button() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie")

    bob.all_in = True

    session = make_session(alice, bob, charlie)

    # Alice = BTN
    session.table.dealer_index = 0

    hand = make_hand(session)
    hand.street = "FLOP"

    players = get_players_in_betting_order(
        session=session,
        hand=hand,
    )

    assert players == [
        charlie,
        alice,
    ]


def test_three_player_preflop_order_is_button_then_sb_then_bb() -> None:
    alice = make_player("Alice", stack=100)
    bob = make_player("Bob", stack=100)
    charlie = make_player("Charlie", stack=100)

    session = make_session(
        alice,
        bob,
        charlie,
    )

    # Alice = BTN
    session.table.dealer_index = 0

    hand = make_hand(
        session,
        current_bet=10,
    )
    hand.street = "PREFLOP"

    # Alice is immediately left of BB.
    hand.first_to_act = alice

    alice.current_bet = 0
    bob.current_bet = 5
    charlie.current_bet = 10

    with patch(
        "backend.game.betting.ask_player_action",
        side_effect=[
            ("call", None),
            ("call", None),
            ("check", None),
        ],
    ) as mock_action:
        betting_round(
            session=session,
            hand=hand,
        )

    called_players = [call.kwargs["player"] for call in mock_action.call_args_list]

    assert called_players == [
        alice,
        bob,
        charlie,
    ]


def test_three_player_postflop_order_is_sb_then_bb_then_button() -> None:
    alice = make_player("Alice", stack=100)
    bob = make_player("Bob", stack=100)
    charlie = make_player("Charlie", stack=100)

    session = make_session(
        alice,
        bob,
        charlie,
    )

    # Alice = BTN
    session.table.dealer_index = 0

    hand = make_hand(session)
    hand.street = "FLOP"

    with patch(
        "backend.game.betting.ask_player_action",
        side_effect=[
            ("check", None),
            ("check", None),
            ("check", None),
        ],
    ) as mock_action:
        betting_round(
            session=session,
            hand=hand,
        )

    called_players = [call.kwargs["player"] for call in mock_action.call_args_list]

    assert called_players == [
        bob,
        charlie,
        alice,
    ]


def test_heads_up_preflop_starts_with_button_small_blind() -> None:
    alice = make_player("Alice", stack=100)
    bob = make_player("Bob", stack=100)

    session = make_session(
        alice,
        bob,
    )

    session.table.dealer_index = 0

    hand = make_hand(
        session,
        current_bet=10,
    )
    hand.street = "PREFLOP"
    hand.first_to_act = alice

    result = get_players_in_betting_order(
        session=session,
        hand=hand,
    )

    assert result == [
        alice,
        bob,
    ]


def test_heads_up_postflop_starts_with_big_blind() -> None:
    alice = make_player("Alice", stack=100)
    bob = make_player("Bob", stack=100)

    session = make_session(
        alice,
        bob,
    )

    # Alice = BTN/SB
    session.table.dealer_index = 0

    hand = make_hand(session)
    hand.street = "FLOP"

    result = get_players_in_betting_order(
        session=session,
        hand=hand,
    )

    assert result == [
        bob,
        alice,
    ]


# ============================================================
# Betting order
# ============================================================


def test_preflop_betting_starts_at_first_to_act() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    hand = make_hand(session)
    hand.street = "PREFLOP"
    hand.first_to_act = charlie

    result = get_players_in_betting_order(
        session=session,
        hand=hand,
    )

    assert result == [
        charlie,
        alice,
        bob,
    ]


def test_postflop_betting_starts_left_of_dealer() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    session.table.dealer_index = 0

    hand = make_hand(session)
    hand.street = "FLOP"

    result = get_players_in_betting_order(
        session=session,
        hand=hand,
    )

    assert result == [
        bob,
        charlie,
        alice,
    ]


def test_betting_order_excludes_players_who_cannot_act() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    bob.folded = True

    session = make_session(
        alice,
        bob,
        charlie,
    )

    hand = make_hand(session)
    hand.street = "PREFLOP"
    hand.first_to_act = alice

    result = get_players_in_betting_order(
        session=session,
        hand=hand,
    )

    assert result == [
        alice,
        charlie,
    ]


# ============================================================
# Allowed actions
# ============================================================


def test_allowed_actions_when_player_can_check() -> None:
    player = make_player("Alice", stack=100)

    session = make_session(player)
    hand = make_hand(
        session,
        current_bet=20,
    )

    player.current_bet = 20

    actions = get_allowed_actions(
        player=player,
        hand=hand,
    )

    assert actions == [
        "fold",
        "check",
        "raise",
        "all_in",
    ]


def test_allowed_actions_when_player_must_call() -> None:
    player = make_player("Alice", stack=100)

    session = make_session(player)
    hand = make_hand(
        session,
        current_bet=20,
    )

    player.current_bet = 10
    hand.last_raise_size = 10

    actions = get_allowed_actions(
        player=player,
        hand=hand,
    )

    assert actions == [
        "fold",
        "call",
        "raise",
        "all_in",
    ]


def test_allowed_actions_when_call_uses_entire_stack() -> None:
    alice = make_player("Alice", stack=5)

    session = make_session(alice)

    hand = make_hand(
        session,
        current_bet=10,
    )

    alice.current_bet = 5

    actions = get_allowed_actions(
        player=alice,
        hand=hand,
    )

    assert "fold" in actions
    assert "call" in actions
    assert "check" not in actions
    assert "all_in" not in actions


def test_allowed_actions_when_player_cannot_make_minimum_raise() -> None:
    player = make_player("Alice", stack=5)

    session = make_session(player)
    hand = make_hand(
        session,
        current_bet=20,
    )

    player.current_bet = 20
    hand.last_raise_size = 10

    actions = get_allowed_actions(
        player=player,
        hand=hand,
    )

    assert actions == [
        "fold",
        "check",
        "all_in",
    ]


def test_allowed_actions_when_call_requires_all_stack() -> None:
    player = make_player("Alice", stack=10)

    session = make_session(player)
    hand = make_hand(
        session,
        current_bet=30,
    )

    player.current_bet = 20

    actions = get_allowed_actions(
        player=player,
        hand=hand,
    )

    assert "call" in actions
    assert "raise" not in actions
    assert "all_in" not in actions


# ============================================================
# betting_round_can_continue
# ============================================================


def test_betting_round_can_continue_with_two_players_who_can_act() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")

    session = make_session(
        alice,
        bob,
    )

    hand = make_hand(session)

    assert betting_round_can_continue(hand) is True


def test_betting_round_cannot_continue_when_everyone_is_all_in() -> None:
    alice = make_player("Alice", stack=0)
    bob = make_player("Bob", stack=0)

    alice.all_in = True
    bob.all_in = True

    session = make_session(
        alice,
        bob,
    )

    hand = make_hand(session)

    assert betting_round_can_continue(hand) is False


def test_betting_round_cannot_continue_when_only_one_player_can_act_and_matches_bet() -> (
    None
):
    alice = make_player("Alice")
    bob = make_player("Bob", stack=0)

    bob.all_in = True

    session = make_session(
        alice,
        bob,
    )

    hand = make_hand(
        session,
        current_bet=20,
    )

    alice.current_bet = 20

    assert betting_round_can_continue(hand) is False


def test_betting_round_can_continue_when_only_one_player_needs_to_call() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob", stack=0)

    bob.all_in = True

    session = make_session(
        alice,
        bob,
    )

    hand = make_hand(
        session,
        current_bet=30,
    )

    alice.current_bet = 20

    assert betting_round_can_continue(hand) is True


# ============================================================
# count_remaining_players
# ============================================================


def test_count_remaining_players_excludes_folded_players() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    bob.folded = True

    session = make_session(
        alice,
        bob,
        charlie,
    )

    hand = make_hand(session)

    assert count_remaining_players(hand) == 2


def test_count_remaining_players_keeps_all_in_players() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob", stack=0)

    bob.all_in = True

    session = make_session(
        alice,
        bob,
    )

    hand = make_hand(session)

    assert count_remaining_players(hand) == 2


# ============================================================
# finish_by_fold
# ============================================================


def test_finish_by_fold_sets_winner() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")

    bob.folded = True

    session = make_session(
        alice,
        bob,
    )

    hand = make_hand(
        session,
        current_bet=20,
    )

    result = finish_by_fold(hand)

    assert result is False
    assert hand.winner_by_fold is alice
    assert hand.finished is True
    assert hand.current_player is None


def test_finish_by_fold_returns_false_when_multiple_players_remain() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")

    session = make_session(
        alice,
        bob,
    )

    hand = make_hand(session)

    result = finish_by_fold(hand)

    assert result is False
    assert hand.finished is False
    assert hand.winner_by_fold is None


# ============================================================
# Complete betting round — check
# ============================================================


def test_betting_round_all_players_check() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    hand = make_hand(session)
    hand.street = "FLOP"

    alice.current_bet = 0
    bob.current_bet = 0
    charlie.current_bet = 0

    with patch(
        "backend.game.betting.ask_player_action",
        side_effect=[
            ("check", None),
            ("check", None),
            ("check", None),
        ],
    ):
        result = betting_round(
            session=session,
            hand=hand,
        )

    assert result is True
    assert hand.finished is False
    assert hand.current_player is None
    assert hand.last_player_to_act is alice

    assert alice.acted_this_round is True
    assert bob.acted_this_round is True
    assert charlie.acted_this_round is True


# ============================================================
# Complete betting round — call
# ============================================================


def test_betting_round_all_players_call() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    hand = make_hand(
        session,
        current_bet=10,
    )
    hand.street = "PREFLOP"

    hand.first_to_act = alice

    alice.current_bet = 0
    bob.current_bet = 0
    charlie.current_bet = 10

    with patch(
        "backend.game.betting.ask_player_action",
        side_effect=[
            ("call", None),
            ("call", None),
            ("check", None),
        ],
    ):
        result = betting_round(
            session=session,
            hand=hand,
        )

    assert result is True
    assert hand.current_player is None

    assert alice.current_bet == 10
    assert bob.current_bet == 10

    assert alice.stack == 90
    assert bob.stack == 90

    assert hand.pot == 20

    assert hand.last_player_to_act is charlie


# ============================================================
# Complete betting round — fold
# ============================================================


def test_betting_round_ends_when_all_but_one_player_fold() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    hand = make_hand(session)
    hand.street = "FLOP"

    with patch(
        "backend.game.betting.ask_player_action",
        side_effect=[
            ("fold", None),
            ("fold", None),
        ],
    ):
        result = betting_round(
            session=session,
            hand=hand,
        )

    assert result is False
    assert hand.finished is True
    assert hand.winner_by_fold is alice
    assert hand.current_player is None


# ============================================================
# Complete betting round — raise
# ============================================================


def test_betting_round_raise_reopens_action() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    hand = make_hand(
        session,
        current_bet=10,
    )
    hand.street = "PREFLOP"
    hand.first_to_act = alice
    hand.last_raise_size = 10

    # Everyone has already posted/matched the blind.
    alice.current_bet = 10
    bob.current_bet = 10
    charlie.current_bet = 10

    with patch(
        "backend.game.betting.ask_player_action",
        side_effect=[
            ("raise", 20),
            ("call", None),
            ("call", None),
        ],
    ) as mock_action:
        result = betting_round(
            session=session,
            hand=hand,
        )

    assert result is True

    assert mock_action.call_count == 3

    assert alice.current_bet == 20
    assert bob.current_bet == 20
    assert charlie.current_bet == 20

    assert hand.current_bet == 20
    assert hand.last_raise_size == 10
    assert hand.last_raiser is alice

    assert hand.last_player_to_act is charlie


# ============================================================
# Raise order regression test
# ============================================================


def test_raise_does_not_restart_action_from_first_player() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")
    charlie = make_player("Charlie")

    session = make_session(
        alice,
        bob,
        charlie,
    )

    hand = make_hand(
        session,
        current_bet=10,
    )

    hand.street = "PREFLOP"
    hand.first_to_act = alice
    hand.last_raise_size = 10

    alice.current_bet = 10
    bob.current_bet = 10
    charlie.current_bet = 10

    with patch(
        "backend.game.betting.ask_player_action",
        side_effect=[
            ("raise", 20),
            ("call", None),
            ("call", None),
        ],
    ) as mock_action:
        betting_round(
            session=session,
            hand=hand,
        )

    called_players = [call.kwargs["player"] for call in mock_action.call_args_list]

    assert called_players == [
        alice,
        bob,
        charlie,
    ]


# ============================================================
# All-in player is skipped
# ============================================================


def test_betting_round_skips_all_in_players() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie")

    bob.all_in = True
    bob.current_bet = 20

    session = make_session(
        alice,
        bob,
        charlie,
    )

    hand = make_hand(
        session,
        current_bet=20,
    )

    hand.street = "FLOP"

    alice.current_bet = 20
    charlie.current_bet = 20

    with patch(
        "backend.game.betting.ask_player_action",
        side_effect=[
            ("check", None),
            ("check", None),
        ],
    ) as mock_action:
        result = betting_round(
            session=session,
            hand=hand,
        )

    assert result is True

    called_players = [call.kwargs["player"] for call in mock_action.call_args_list]

    assert called_players == [
        charlie,
        alice,
    ]


def test_all_in_player_is_skipped_without_changing_clockwise_order() -> None:
    alice = make_player("Alice", stack=100)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=100)
    dave = make_player("Dave", stack=100)

    bob.all_in = True

    session = make_session(
        alice,
        bob,
        charlie,
        dave,
    )

    # Alice = BTN
    session.table.dealer_index = 0

    hand = make_hand(session)
    hand.street = "FLOP"

    result = get_players_in_betting_order(
        session=session,
        hand=hand,
    )

    assert result == [
        charlie,
        dave,
        alice,
    ]


# ============================================================
# Player state after actions
# ============================================================


def test_betting_round_updates_last_player_to_act() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")

    session = make_session(
        alice,
        bob,
    )

    hand = make_hand(session)
    hand.street = "FLOP"

    with patch(
        "backend.game.betting.ask_player_action",
        side_effect=[
            ("check", None),
            ("check", None),
        ],
    ):
        betting_round(
            session=session,
            hand=hand,
        )

    assert hand.last_player_to_act is alice


def test_betting_round_clears_current_player_when_finished() -> None:
    alice = make_player("Alice")
    bob = make_player("Bob")

    session = make_session(
        alice,
        bob,
    )

    hand = make_hand(session)
    hand.street = "FLOP"

    with patch(
        "backend.game.betting.ask_player_action",
        side_effect=[
            ("check", None),
            ("check", None),
        ],
    ):
        betting_round(
            session=session,
            hand=hand,
        )

    assert hand.current_player is None


def test_betting_round_stops_when_only_remaining_player_is_already_matched() -> None:
    alice = make_player("Alice", stack=100)
    bob = make_player("Bob", stack=0)
    charlie = make_player("Charlie", stack=0)

    bob.all_in = True
    charlie.all_in = True

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
    hand.street = "FLOP"

    alice.current_bet = 20
    bob.current_bet = 20
    charlie.current_bet = 20

    with patch(
        "backend.game.betting.ask_player_action",
    ) as mock_action:
        result = betting_round(
            session=session,
            hand=hand,
        )

    assert result is True
    assert mock_action.called is False
    assert hand.current_player is None
