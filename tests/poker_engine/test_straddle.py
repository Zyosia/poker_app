"""The straddle (V3.0): a blind raise to two big blinds by the player under
the gun, and chips added between hands."""

import pytest

from backend.poker_engine.actions import Action
from backend.poker_engine.betting import apply_action, get_current_legal_actions
from backend.poker_engine.constants import ActionType, Position, Street
from backend.poker_engine.hand import advance_hand, start_hand
from backend.poker_engine.models import Hand
from backend.poker_engine.session import GameConfig, GameSession, create_session

NAMES = ["Alice", "Bob", "Charlie", "Dave", "Eve", "Frank"]
STRADDLE = GameConfig(starting_stack=1000, small_blind=5, big_blind=10, straddle=True)


def straddled_session(
    names: list[str] = NAMES, config: GameConfig = STRADDLE
) -> GameSession:
    session = create_session(names, config)
    session.table.dealer_index = 0  # Alice is the Button.
    return session


def act(hand: Hand, name: str, action: ActionType, amount: int | None = None) -> None:
    assert hand.current_player is not None
    assert hand.current_player.name == name
    apply_action(hand, Action(type=action, amount=amount))


def test_the_player_under_the_gun_posts_two_big_blinds() -> None:
    session = straddled_session()
    hand = start_hand(session)
    dave = session.players[3]

    assert dave.position == Position.UTG
    assert [e.action for e in hand.actions] == ["post_sb", "post_bb", "post_straddle"]
    assert hand.actions[-1].player == "Dave" and hand.actions[-1].amount == 20
    assert dave.stack == 980 and dave.current_bet == 20
    assert hand.current_bet == 20
    assert hand.pot == 35


def test_the_action_starts_left_of_the_straddler_who_acts_last() -> None:
    session = straddled_session()
    hand = start_hand(session)

    assert hand.first_to_act is session.players[4]  # Eve, left of Dave.
    assert hand.current_player is session.players[4]

    for name in ("Eve", "Frank", "Alice"):
        act(hand, name, ActionType.FOLD)

    act(hand, "Bob", ActionType.CALL)  # The small blind completes to 20.
    act(hand, "Charlie", ActionType.CALL)  # The big blind adds 10.

    # Everyone matched the straddle: the straddler still has the option.
    assert hand.current_player is session.players[3]
    legal = {a.type for a in get_current_legal_actions(hand)}
    assert ActionType.CHECK in legal and ActionType.RAISE in legal

    act(hand, "Dave", ActionType.CHECK)
    assert hand.current_player is None
    advance_hand(hand)
    assert hand.street == Street.FLOP
    assert hand.pot == 60


def test_the_minimum_raise_is_to_twice_the_straddle() -> None:
    session = straddled_session()
    hand = start_hand(session)

    raise_action = next(
        a for a in get_current_legal_actions(hand) if a.type == ActionType.RAISE
    )

    assert raise_action.min_amount == 40


def test_after_the_flop_the_order_is_unchanged() -> None:
    session = straddled_session()
    hand = start_hand(session)

    for name in ("Eve", "Frank", "Alice", "Bob"):
        act(hand, name, ActionType.FOLD)

    act(hand, "Charlie", ActionType.CALL)
    act(hand, "Dave", ActionType.CHECK)
    advance_hand(hand)

    assert hand.current_player is session.players[2]  # Charlie, the big blind.


def test_three_handed_the_button_straddles() -> None:
    session = straddled_session(NAMES[:3])
    hand = start_hand(session)

    assert hand.actions[-1].action == "post_straddle"
    assert hand.actions[-1].player == "Alice"  # The Button acts first.
    assert hand.current_player is session.players[1]  # Bob, the small blind.


def test_there_is_no_straddle_heads_up_or_when_it_would_be_all_in() -> None:
    heads_up = straddled_session(NAMES[:2])
    assert "post_straddle" not in [e.action for e in start_hand(heads_up).actions]

    short = straddled_session()
    short.players[3].stack = 20  # Dave could only straddle all-in.
    hand = start_hand(short)

    assert "post_straddle" not in [e.action for e in hand.actions]
    assert hand.current_bet == 10
    assert hand.current_player is short.players[3]


def test_without_the_option_nothing_changes() -> None:
    session = create_session(NAMES, GameConfig())
    session.table.dealer_index = 0
    hand = start_hand(session)

    assert [e.action for e in hand.actions] == ["post_sb", "post_bb"]
    assert hand.current_player is session.players[3]


def test_chips_are_conserved_in_a_straddled_hand() -> None:
    session = straddled_session()
    hand = start_hand(session)
    total = sum(p.stack for p in session.players) + hand.pot

    act(hand, "Eve", ActionType.RAISE, 60)

    for name in ("Frank", "Alice", "Bob", "Charlie"):
        act(hand, name, ActionType.FOLD)

    act(hand, "Dave", ActionType.CALL)

    while not hand.finished:
        if hand.current_player is None:
            advance_hand(hand)
        else:
            act(hand, hand.current_player.name, ActionType.CHECK)

    assert sum(p.stack for p in session.players) == total


# --- Chips added between hands -----------------------------------------------------


def test_a_top_up_adds_chips_between_hands_only() -> None:
    session = create_session(NAMES[:3], GameConfig())
    session.table.dealer_index = 0
    alice = session.players[0]

    session.add_chips(alice, 250)
    assert alice.stack == 1250

    hand = start_hand(session)
    with pytest.raises(RuntimeError, match="between hands"):
        session.add_chips(alice, 100)

    hand.finished = True  # The hand is over.
    session.add_chips(alice, 100)

    with pytest.raises(ValueError, match="positive"):
        session.add_chips(alice, 0)


def test_a_busted_player_rebuys_the_amount_chosen() -> None:
    session = create_session(NAMES[:3], GameConfig(rebuy_stack=500))
    alice = session.players[0]
    alice.stack = 0

    with pytest.raises(ValueError, match="rebuy"):
        session.add_chips(alice, 100)

    session.rebuy_player(alice, 800)
    assert alice.stack == 800

    alice.stack = 0
    session.rebuy_player(alice)
    assert alice.stack == 500
