"""The moment no more betting is possible, when the cards are turned face up."""

from backend.application.persistence import serialize_hand
from backend.poker_engine.actions import Action
from backend.poker_engine.betting import apply_action, is_betting_closed
from backend.poker_engine.constants import ActionType, Street
from backend.poker_engine.hand import advance_hand, start_hand
from backend.poker_engine.models import Hand, Player
from backend.poker_engine.session import GameConfig, GameSession, create_session

NAMES = ("Alice", "Bob", "Charlie", "Dana")


def make_table(*stacks: int) -> GameSession:
    """Alice, Bob, ... with the given stacks; Alice has the button. Blinds 5/10."""
    session = create_session(
        player_names=list(NAMES[: len(stacks)]),
        config=GameConfig(small_blind=5, big_blind=10),
    )

    for player, stack in zip(session.players, stacks, strict=True):
        player.stack = stack

    session.table.dealer_index = 0

    return session


def player(hand: Hand, name: str) -> Player:
    return next(p for p in hand.table.players if p.name == name)


def act(hand: Hand, name: str, action: ActionType, amount: int | None = None) -> None:
    assert hand.current_player is not None
    assert hand.current_player.name == name, f"{hand.current_player.name} acts"
    apply_action(hand, Action(type=action, amount=amount))


def test_an_all_in_called_preflop_reveals_before_the_flop() -> None:
    session = make_table(1000, 1000, 1000)
    hand = start_hand(session)
    # Three-handed, the Button (Alice) acts first pre-flop.
    assert hand.first_to_act is player(hand, "Alice")

    act(hand, "Alice", ActionType.ALL_IN)
    act(hand, "Bob", ActionType.FOLD)
    assert hand.revealed_after_action is None, "Charlie can still decide"
    act(hand, "Charlie", ActionType.CALL)

    assert is_betting_closed(hand)
    assert hand.current_player is None
    assert hand.street == Street.PREFLOP and hand.community_cards == []
    assert hand.revealed_after_action == hand.actions[-1].sequence
    assert hand.actions[-1].player == "Charlie"


def test_the_readme_example_reveals_on_the_flop_after_the_last_fold() -> None:
    # Alice Button, Bob Small Blind, Charlie Big Blind, Dana first pre-flop.
    session = make_table(1000, 1000, 1000, 1000)
    hand = start_hand(session)
    assert hand.first_to_act is player(hand, "Dana")

    act(hand, "Dana", ActionType.CALL)
    act(hand, "Alice", ActionType.CALL)
    act(hand, "Bob", ActionType.CALL)
    act(hand, "Charlie", ActionType.CHECK)
    advance_hand(hand)
    assert hand.street == Street.FLOP

    # On the flop: player 1 all-in, player 2 folds, player 3 calls, 4 folds.
    act(hand, "Bob", ActionType.ALL_IN)
    act(hand, "Charlie", ActionType.FOLD)
    act(hand, "Dana", ActionType.CALL)
    assert hand.revealed_after_action is None, "Alice has not acted yet"
    act(hand, "Alice", ActionType.FOLD)

    revealed = hand.revealed_after_action
    assert revealed == hand.actions[-1].sequence
    assert len(hand.community_cards) == 3

    # The turn and the river are dealt one by one, without any decision.
    advance_hand(hand)
    assert hand.street == Street.TURN and hand.current_player is None
    advance_hand(hand)
    assert hand.street == Street.RIVER and hand.current_player is None
    advance_hand(hand)

    assert hand.finished
    assert set(hand.showdown_evaluations) == {"Bob", "Dana"}
    assert hand.revealed_after_action == revealed
    assert not is_betting_closed(hand), "a finished hand has no betting left"


def test_the_player_covering_two_all_ins_closes_the_betting_by_calling() -> None:
    session = make_table(1000, 200, 300)
    hand = start_hand(session)

    act(hand, "Alice", ActionType.RAISE, 100)
    act(hand, "Bob", ActionType.ALL_IN)
    act(hand, "Charlie", ActionType.ALL_IN)
    assert hand.revealed_after_action is None, "Alice still faces the raise"
    act(hand, "Alice", ActionType.CALL)

    assert player(hand, "Alice").stack == 700
    assert is_betting_closed(hand)
    assert hand.revealed_after_action == hand.actions[-1].sequence


def test_no_reveal_while_two_players_can_still_bet() -> None:
    session = make_table(1000, 100, 1000)
    hand = start_hand(session)

    act(hand, "Alice", ActionType.CALL)
    act(hand, "Bob", ActionType.ALL_IN)
    act(hand, "Charlie", ActionType.CALL)
    act(hand, "Alice", ActionType.CALL)
    assert hand.current_player is None  # The pre-flop round is over…

    assert not is_betting_closed(hand)  # …but Alice and Charlie can still bet.
    assert hand.revealed_after_action is None

    advance_hand(hand)
    assert hand.street == Street.FLOP
    assert hand.current_player is not None
    assert hand.revealed_after_action is None


def test_folding_to_an_all_in_reveals_nothing() -> None:
    session = make_table(1000, 1000, 1000)
    hand = start_hand(session)

    act(hand, "Alice", ActionType.ALL_IN)
    act(hand, "Bob", ActionType.FOLD)
    act(hand, "Charlie", ActionType.FOLD)

    assert hand.finished and hand.winner_by_fold is player(hand, "Alice")
    assert hand.revealed_after_action is None
    assert not is_betting_closed(hand)


def test_blinds_putting_everyone_all_in_reveal_at_once() -> None:
    # Heads-up, the Button (Alice) posts the small blind.
    session = make_table(5, 10)
    hand = start_hand(session)

    assert hand.current_player is None
    assert is_betting_closed(hand)
    assert hand.revealed_after_action == len(hand.actions) == 2


def test_the_history_records_the_reveal_after_the_right_action() -> None:
    session = make_table(1000, 1000, 1000)
    hand = start_hand(session)
    act(hand, "Alice", ActionType.ALL_IN)
    act(hand, "Bob", ActionType.CALL)
    act(hand, "Charlie", ActionType.FOLD)

    while not hand.finished:
        advance_hand(hand)

    data = serialize_hand(hand, hand_number=1)
    revealed = data["revealed_after_action"]

    # Recorded right after Charlie's fold, the last decision of the hand,
    # before any community card.
    assert revealed == 5
    assert data["actions"][revealed - 1]["player"] == "Charlie"
    assert data["actions"][revealed - 1]["action"] == ActionType.FOLD
    assert len(data["actions"]) == revealed
    assert data["streets"][0]["street"] == Street.PREFLOP
    assert data["timed_out_actions"] == []
