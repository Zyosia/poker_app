from backend.poker_engine.constants import Position, Street
from backend.poker_engine.history import (
    record_action,
    record_street,
)
from tests.helpers import make_session_with_hand


def test_record_action_stores_action_details():
    session, hand = make_session_with_hand()

    player = session.players[0]

    player.current_bet = 10

    hand.current_bet = 10
    hand.pot = 30

    record_action(
        hand=hand,
        player=player,
        action="call",
        amount=10,
        bet_before=0,
    )

    assert len(hand.actions) == 1

    event = hand.actions[0]

    assert event.sequence == 1
    assert event.street == "PREFLOP"
    assert event.player == "Alice"
    assert event.position is None
    assert event.action == "call"
    assert event.amount == 10
    assert event.bet_before == 0
    assert event.bet_after == 10
    assert event.pot_after == 30
    assert event.current_bet_after == 10
    assert event.bet_initiator is False


def test_record_action_sequences_are_incremental():
    session, hand = make_session_with_hand()

    player = session.players[0]

    for action in ("check", "call", "fold"):
        record_action(
            hand=hand,
            player=player,
            action=action,
            amount=0,
            bet_before=0,
        )

    assert [event.sequence for event in hand.actions] == [1, 2, 3]


def test_record_action_also_records_pot_history():
    session, hand = make_session_with_hand()

    player = session.players[0]

    hand.pot = 25

    record_action(
        hand=hand,
        player=player,
        action="call",
        amount=10,
        bet_before=0,
    )

    assert len(hand.pot_history) == 1

    pot_event = hand.pot_history[0]

    assert pot_event.sequence == 1
    assert pot_event.street == "PREFLOP"
    assert pot_event.amount == 25


def test_pot_history_follows_every_recorded_action():
    session, hand = make_session_with_hand()
    alice, bob, _ = session.players

    for pot, (player, street) in enumerate(
        [(alice, Street.PREFLOP), (bob, Street.PREFLOP), (alice, Street.FLOP)],
        start=1,
    ):
        hand.street = street
        hand.pot = pot * 10
        record_action(hand=hand, player=player, action="call", amount=10, bet_before=0)

    assert [(e.sequence, e.street, e.amount) for e in hand.pot_history] == [
        (1, Street.PREFLOP, 10),
        (2, Street.PREFLOP, 20),
        (3, Street.FLOP, 30),
    ]


def test_record_street_stores_community_cards_snapshot():
    _, hand = make_session_with_hand()

    hand.street = Street.FLOP
    hand.community_cards.extend(
        ["AS", "KD", "7C"],
    )

    record_street(hand)

    assert len(hand.streets) == 1

    event = hand.streets[0]

    assert event.street == "FLOP"
    assert event.community_cards == (
        "AS",
        "KD",
        "7C",
    )


def test_record_street_keeps_previous_snapshot():
    _, hand = make_session_with_hand()

    hand.street = Street.FLOP
    hand.community_cards.extend(
        ["AS", "KD", "7C"],
    )

    record_street(hand)

    hand.street = Street.TURN
    hand.community_cards.append("2H")

    record_street(hand)

    assert hand.streets[0].community_cards == (
        "AS",
        "KD",
        "7C",
    )

    assert hand.streets[1].community_cards == (
        "AS",
        "KD",
        "7C",
        "2H",
    )


def test_raise_can_be_recorded_as_bet_initiator():
    session, hand = make_session_with_hand()

    player = session.players[0]

    player.current_bet = 30
    hand.current_bet = 30
    hand.pot = 60

    record_action(
        hand=hand,
        player=player,
        action="raise",
        amount=30,
        bet_before=0,
        bet_initiator=True,
    )

    event = hand.actions[0]

    assert event.action == "raise"
    assert event.amount == 30
    assert event.bet_initiator is True


def test_hand_history_records_realistic_preflop_sequence():
    session, hand = make_session_with_hand()

    alice, bob, charlie = session.players

    alice.position = Position.BTN
    bob.position = Position.SB
    charlie.position = Position.BB

    hand.current_bet = 10
    hand.pot = 15

    record_action(
        hand=hand,
        player=bob,
        action="post_sb",
        amount=5,
        bet_before=0,
    )

    record_action(
        hand=hand,
        player=charlie,
        action="post_bb",
        amount=10,
        bet_before=0,
        bet_initiator=True,
    )

    record_action(
        hand=hand,
        player=alice,
        action="call",
        amount=10,
        bet_before=0,
    )

    record_action(
        hand=hand,
        player=bob,
        action="call",
        amount=5,
        bet_before=5,
    )

    record_action(
        hand=hand,
        player=charlie,
        action="check",
        amount=0,
        bet_before=10,
    )

    assert [event.player for event in hand.actions] == [
        "Bob",
        "Charlie",
        "Alice",
        "Bob",
        "Charlie",
    ]

    assert [event.action for event in hand.actions] == [
        "post_sb",
        "post_bb",
        "call",
        "call",
        "check",
    ]

    assert hand.actions[1].bet_initiator is True

    assert [event.sequence for event in hand.actions] == [1, 2, 3, 4, 5]
