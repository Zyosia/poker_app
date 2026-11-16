"""Step-by-step lifecycle of a hand: blinds, dealing, streets and showdown."""

import random

import pytest

from backend.poker_engine.betting import apply_action
from backend.poker_engine.deck import Deck
from backend.poker_engine.hand import advance_hand, play_hand, start_hand
from backend.poker_engine.session import GameConfig, create_session
from tests.helpers import allowed_action_types, scripted_actions, to_action

CONFIG = GameConfig(starting_stack=100, small_blind=5, big_blind=10)


def test_start_hand_posts_blinds_and_deals_two_cards_each() -> None:
    session = create_session(["Alice", "Bob", "Charlie"], CONFIG)
    session.table.dealer_index = 0
    alice, bob, charlie = session.players

    hand = start_hand(session)

    assert session.hands == [hand]
    assert hand.street == "PREFLOP"
    assert hand.min_bet == 10

    assert [player.position for player in session.players] == ["BTN", "SB", "BB"]
    assert bob.current_bet == 5
    assert charlie.current_bet == 10
    assert hand.pot == 15
    assert hand.current_bet == 10

    assert all(len(player.hand) == 2 for player in session.players)
    assert hand.deck.remaining_cards == 46

    # Three-handed, the Button is left of the Big Blind and acts first.
    assert hand.first_to_act is alice
    assert hand.current_player is alice


def test_heads_up_button_posts_small_blind_and_acts_first_preflop() -> None:
    session = create_session(["Alice", "Bob"], CONFIG)
    session.table.dealer_index = 0
    alice, bob = session.players

    hand = start_hand(session)

    assert alice.position == "BTN"
    assert alice.current_bet == 5
    assert bob.position == "BB"
    assert bob.current_bet == 10
    assert hand.first_to_act is alice
    assert hand.current_player is alice

    apply_action(hand, to_action(("call", None)))
    apply_action(hand, to_action(("check", None)))
    advance_hand(hand)

    # Post-flop the Big Blind acts first and the Button last.
    assert hand.street == "FLOP"
    assert hand.current_player is bob


def test_advance_hand_deals_one_street_at_a_time() -> None:
    session = create_session(["Alice", "Bob"], CONFIG)
    session.table.dealer_index = 0

    hand = start_hand(session)

    apply_action(hand, to_action(("all_in", None)))
    apply_action(hand, to_action(("call", None)))

    # Both players are all-in: no decision remains, the board runs out.
    assert hand.current_player is None
    assert hand.finished is False

    expected_board_sizes = {"FLOP": 3, "TURN": 4, "RIVER": 5}

    for street, board_size in expected_board_sizes.items():
        advance_hand(hand)

        assert hand.street == street
        assert len(hand.community_cards) == board_size
        assert hand.current_player is None
        assert hand.finished is False

    advance_hand(hand)

    assert hand.finished is True
    assert hand.pot == 0
    assert sum(player.stack for player in session.players) == 200
    assert [event.street for event in hand.streets] == [
        "PREFLOP",
        "FLOP",
        "TURN",
        "RIVER",
    ]


def test_advance_hand_is_rejected_during_a_betting_round() -> None:
    session = create_session(["Alice", "Bob"], CONFIG)
    session.table.dealer_index = 0

    hand = start_hand(session)

    with pytest.raises(RuntimeError):
        advance_hand(hand)


def test_advance_hand_is_rejected_once_the_hand_is_finished() -> None:
    session = create_session(["Alice", "Bob"], CONFIG)
    session.table.dealer_index = 0

    hand = start_hand(session)
    apply_action(hand, to_action(("fold", None)))

    assert hand.finished is True

    with pytest.raises(RuntimeError):
        advance_hand(hand)


def test_seeded_deck_makes_a_hand_reproducible() -> None:
    boards = []

    for _ in range(2):
        session = create_session(["Alice", "Bob"], CONFIG)
        session.table.dealer_index = 0

        hand = play_hand(
            session,
            scripted_actions([("all_in", None), ("call", None)]),
            deck=Deck(random.Random(7)),
        )
        boards.append((hand.community_cards, [p.hand for p in session.players]))

    assert boards[0] == boards[1]


# ============================================================
# Short blinds
# ============================================================


def test_short_big_blind_still_requires_a_full_big_blind_call() -> None:
    session = create_session(["Alice", "Bob", "Charlie"], CONFIG)
    session.table.dealer_index = 0
    alice, bob, charlie = session.players
    charlie.stack = 4

    hand = start_hand(session)

    assert charlie.position == "BB"
    assert charlie.current_bet == 4
    assert charlie.all_in is True
    assert len(charlie.hand) == 2

    # The bet to call is the full big blind, and a raise is to 20 at least.
    assert hand.current_bet == 10
    assert hand.current_player is alice

    apply_action(hand, to_action(("call", None)))

    assert alice.current_bet == 10
    assert hand.current_player is bob

    apply_action(hand, to_action(("call", None)))

    assert hand.current_player is None
    assert sum(p.stack for p in session.players) + hand.pot == 204


def test_heads_up_short_big_blind_needs_no_action() -> None:
    session = create_session(["Alice", "Bob"], CONFIG)
    session.table.dealer_index = 0
    alice, bob = session.players
    bob.stack = 3

    hand = play_hand(session, scripted_actions([]))

    # Alice's small blind already covers Bob's all-in: the hand runs out and
    # the 2 chips Bob could not match come back to Alice.
    assert hand.finished is True
    assert len(hand.community_cards) == 5
    assert alice.stack + bob.stack == 103
    assert alice.stack in {97, 100, 103}


def test_player_all_in_from_the_small_blind_is_dealt_in() -> None:
    session = create_session(["Alice", "Bob", "Charlie"], CONFIG)
    session.table.dealer_index = 0
    alice, bob, charlie = session.players
    bob.stack = 5

    hand = start_hand(session)

    assert bob.all_in is True
    assert len(bob.hand) == 2
    assert bob in hand.table.get_active_players()


# ============================================================
# Players who are not dealt in
# ============================================================


def test_eliminated_player_is_not_dealt_in_and_cannot_win() -> None:
    session = create_session(["Alice", "Bob", "Charlie"], CONFIG)
    session.table.dealer_index = 0
    alice, bob, charlie = session.players
    bob.stack = 0
    bob.eliminated = True

    hand = start_hand(session)

    assert bob.hand == []
    assert bob.position is None
    assert bob not in hand.table.get_active_players()

    # Heads-up between Alice (Button) and Charlie.
    assert alice.position == "BTN"
    assert charlie.position == "BB"
    assert hand.current_player is alice

    apply_action(hand, to_action(("fold", None)))

    assert hand.finished is True
    assert hand.winner_by_fold is charlie
    assert charlie.stack == 105
    assert bob.stack == 0


def test_consecutive_hands_move_the_button_past_eliminated_players() -> None:
    session = create_session(["Alice", "Bob", "Charlie"], CONFIG)
    session.table.dealer_index = 0
    alice, bob, charlie = session.players
    bob.stack = 0
    bob.eliminated = True

    play_hand(session, scripted_actions([("fold", None)]))
    session.table.move_dealer()

    assert session.table.dealer is charlie

    hand = start_hand(session)

    assert charlie.position == "BTN"
    assert alice.position == "BB"
    assert hand.first_to_act is charlie
    assert hand.current_player is charlie
    assert allowed_action_types(charlie, hand) == ["fold", "call", "raise", "all_in"]
