"""Antes: dead money, posting order with short stacks, pots and conservation."""

import random

import pytest

from backend.poker_engine.actions import Action
from backend.poker_engine.betting import apply_action, get_legal_actions
from backend.poker_engine.blinds import AnteType, BlindLevel
from backend.poker_engine.constants import ActionType, Position
from backend.poker_engine.deck import Deck
from backend.poker_engine.hand import advance_hand, play_hand, start_hand
from backend.poker_engine.models import Hand, Player
from backend.poker_engine.pots import build_pots
from backend.poker_engine.session import GameConfig, GameSession, create_session
from tests.helpers import scripted_actions, stacked_deck

CLASSIC = BlindLevel(small_blind=5, big_blind=10, ante=10)
BIG_BLIND_ANTE = BlindLevel(
    small_blind=5, big_blind=10, ante=10, ante_type=AnteType.BIG_BLIND
)


def make_table(
    stacks: list[int], level: BlindLevel, dealer_index: int = 0
) -> GameSession:
    """Players Alice, Bob, Charlie, ... with the given stacks."""
    names = ["Alice", "Bob", "Charlie", "Dana", "Elio", "Fiona"][: len(stacks)]
    session = create_session(
        player_names=names, config=GameConfig(small_blind=5, big_blind=10)
    )

    for player, stack in zip(session.players, stacks, strict=True):
        player.stack = stack

    session.table.dealer_index = dealer_index
    session.set_blind_level(level)

    return session


def player(session: GameSession, name: str) -> Player:
    return next(p for p in session.players if p.name == name)


def forced_bets(hand: Hand) -> list[tuple[str, str, int]]:
    return [(event.player, event.action, event.amount) for event in hand.actions]


# --- Deep stacks ---------------------------------------------------------


def test_classic_antes_are_posted_by_everyone_before_the_blinds() -> None:
    # Alice is the Button, Bob the Small Blind, Charlie the Big Blind.
    session = make_table([1000, 1000, 1000], CLASSIC)

    hand = start_hand(session)

    assert forced_bets(hand) == [
        ("Bob", "post_ante", 10),
        ("Charlie", "post_ante", 10),
        ("Alice", "post_ante", 10),
        ("Bob", "post_sb", 5),
        ("Charlie", "post_bb", 10),
    ]
    assert hand.pot == 45
    assert hand.blind_level == CLASSIC


def test_antes_count_neither_toward_the_call_nor_toward_raises() -> None:
    session = make_table([1000, 1000, 1000], CLASSIC)
    hand = start_hand(session)
    alice = player(session, "Alice")

    assert hand.current_player is alice
    assert hand.current_bet == 10
    assert alice.current_bet == 0
    assert alice.total_contribution == 10

    legal = {action.type: action for action in get_legal_actions(alice, hand)}

    assert legal[ActionType.CALL].amount == 10
    assert legal[ActionType.RAISE].min_amount == 20
    assert legal[ActionType.RAISE].max_amount == 990  # 1000 - 10 of ante.


def test_big_blind_ante_is_posted_by_the_big_blind_after_the_blind() -> None:
    session = make_table([1000, 1000, 1000], BIG_BLIND_ANTE)

    hand = start_hand(session)

    assert forced_bets(hand) == [
        ("Bob", "post_sb", 5),
        ("Charlie", "post_bb", 10),
        ("Charlie", "post_ante", 10),
    ]
    assert hand.pot == 25
    assert player(session, "Charlie").current_bet == 10
    assert player(session, "Charlie").stack == 980


def test_big_blind_ante_heads_up() -> None:
    # Heads-up: Alice is the Button and Small Blind, Bob the Big Blind.
    session = make_table([1000, 1000], BIG_BLIND_ANTE)

    hand = start_hand(session)

    assert player(session, "Alice").position == Position.BTN
    assert forced_bets(hand) == [
        ("Alice", "post_sb", 5),
        ("Bob", "post_bb", 10),
        ("Bob", "post_ante", 10),
    ]
    assert hand.current_player is player(session, "Alice")


def test_the_big_blind_can_check_when_everyone_limps_with_antes() -> None:
    session = make_table([1000, 1000, 1000], CLASSIC)
    hand = start_hand(session)

    apply_action(hand, Action(type=ActionType.CALL))  # Alice
    apply_action(hand, Action(type=ActionType.CALL))  # Bob completes.

    charlie = player(session, "Charlie")
    assert hand.current_player is charlie
    assert ActionType.CHECK in {a.type for a in get_legal_actions(charlie, hand)}


# --- Short stacks --------------------------------------------------------


def test_a_player_short_of_the_ante_is_all_in_and_still_dealt_in() -> None:
    session = make_table([6, 1000, 1000], CLASSIC)
    alice = player(session, "Alice")

    hand = start_hand(session)

    assert ("Alice", "post_ante", 6) in forced_bets(hand)
    assert alice.all_in and alice.stack == 0
    assert len(alice.hand) == 2
    assert not alice.folded
    # Alice cannot act: Bob and Charlie play.
    assert hand.current_player is not alice


def test_a_player_all_in_from_the_ante_can_win_the_main_pot_only() -> None:
    # Alice: ante 6 all-in. Bob and Charlie: ante 10, then all-in for 200.
    session = make_table([6, 210, 210], CLASSIC)
    # Alice gets the nuts; Bob beats Charlie.
    deck = stacked_deck(
        hole_cards={
            "Bob": ("KS", "KH"),
            "Charlie": ("2C", "7D"),
            "Alice": ("AS", "AH"),
        },
        board=("AD", "AC", "KD", "3S", "4H"),
        order=("Bob", "Charlie", "Alice"),
    )

    hand = play_hand(
        session, scripted_actions([("all_in", None), ("call", None)]), deck
    )

    # The main pot holds the three antes Alice could match: 6 x 3.
    assert [pot.amount for pot in hand.pot_results] == [18, 408]
    assert hand.pot_results[0].eligible_players == ("Alice", "Bob", "Charlie")
    assert hand.payouts == {"Alice": 18, "Bob": 408}
    assert [p.stack for p in session.players] == [18, 408, 0]


def test_antes_with_several_side_pots_conserve_every_chip() -> None:
    stacks = [8, 45, 120, 1000]  # Alice is short of the ante.
    session = make_table(stacks, CLASSIC)
    deck = Deck(random.Random(3))

    hand = play_hand(
        session,
        scripted_actions([("all_in", None)] + [("call", None)] * 3),
        deck,
    )

    contributions = {p.name: p.total_contribution for p in session.players}
    assert contributions == {"Alice": 8, "Bob": 45, "Charlie": 120, "Dana": 1000}
    # Main pot, two side pots, and Dana's uncalled chips returned to her.
    assert [pot.amount for pot in hand.pot_results] == [32, 111, 150, 880]
    assert [len(pot.eligible_players) for pot in hand.pot_results] == [4, 3, 2, 1]
    assert sum(p.stack for p in session.players) == sum(stacks)
    assert sum(hand.payouts.values()) == sum(contributions.values())


def test_a_short_big_blind_posts_the_blind_before_the_ante() -> None:
    # Charlie, the Big Blind, has 15 chips: 10 for the blind, 5 of ante.
    session = make_table([1000, 1000, 15], BIG_BLIND_ANTE)

    hand = start_hand(session)

    assert forced_bets(hand) == [
        ("Bob", "post_sb", 5),
        ("Charlie", "post_bb", 10),
        ("Charlie", "post_ante", 5),
    ]
    charlie = player(session, "Charlie")
    assert charlie.all_in and charlie.current_bet == 10
    assert hand.pot == 20
    assert hand.current_bet == 10


def test_a_big_blind_shorter_than_the_blind_posts_no_ante() -> None:
    session = make_table([1000, 1000, 7], BIG_BLIND_ANTE)

    hand = start_hand(session)

    # Nothing is left for the ante, so no ante is recorded.
    assert forced_bets(hand)[-1] == ("Charlie", "post_bb", 7)
    assert hand.pot == 12
    # The bet to call stays the full big blind.
    assert hand.current_bet == 10


def test_a_classic_ante_can_leave_too_little_for_the_blind() -> None:
    # Bob, the Small Blind, has 12: ante 10 first, then 2 of small blind.
    session = make_table([1000, 12, 1000], CLASSIC)

    hand = start_hand(session)

    assert ("Bob", "post_ante", 10) in forced_bets(hand)
    assert ("Bob", "post_sb", 2) in forced_bets(hand)
    assert player(session, "Bob").all_in


def test_everyone_all_in_from_the_antes_runs_the_board_out() -> None:
    session = make_table([10, 10, 10], CLASSIC)

    hand = start_hand(session)

    assert hand.current_player is None
    while not hand.finished:
        advance_hand(hand)

    assert len(hand.community_cards) == 5
    assert sum(p.stack for p in session.players) == 30


# --- Conservation --------------------------------------------------------


@pytest.mark.parametrize("level", [CLASSIC, BIG_BLIND_ANTE], ids=["classic", "bb"])
def test_random_hands_with_antes_conserve_chips(level: BlindLevel) -> None:
    rng = random.Random(level.ante_type)

    for _ in range(300):
        count = rng.randint(2, 6)
        stacks = [rng.choice([3, 9, 14, 25, 60, 400]) for _ in range(count)]
        session = make_table(stacks, level, dealer_index=rng.randrange(count))

        def choose(hand: Hand, actor: Player) -> Action:
            choice = rng.choice(get_legal_actions(actor, hand))

            if choice.type == ActionType.RAISE:
                assert choice.min_amount is not None and choice.max_amount is not None
                return Action(
                    type=choice.type,
                    amount=rng.randint(choice.min_amount, choice.max_amount),
                )

            return Action(type=choice.type)

        hand = play_hand(session, choose, Deck(random.Random(rng.random())))

        assert sum(p.stack for p in session.players) == sum(stacks)
        assert sum(hand.payouts.values()) == hand.dead_money + sum(
            p.total_contribution for p in session.players
        )
        assert all(p.stack >= 0 for p in session.players)


# --- Dead money ----------------------------------------------------------


def test_a_folded_big_blind_ante_stays_in_the_main_pot() -> None:
    # The case found by the random test: Alice (Big Blind) posts 10 and an
    # ante of 10, then folds to two all-ins of 14. Her ante is main-pot
    # money that Bob and Charlie play for.
    session = make_table([400, 14, 14], BIG_BLIND_ANTE, dealer_index=1)
    deck = stacked_deck(
        hole_cards={
            "Charlie": ("AS", "AH"),
            "Alice": ("2C", "7D"),
            "Bob": ("KS", "KH"),
        },
        board=("2D", "5C", "9H", "JS", "3D"),
        order=("Charlie", "Alice", "Bob"),
    )

    hand = play_hand(
        session,
        scripted_actions([("all_in", None), ("call", None), ("fold", None)]),
        deck,
    )

    assert hand.dead_money == 10
    # Main pot: 10 from each player plus the ante; side pot: 4 more each.
    assert [pot.amount for pot in hand.pot_results] == [40, 8]
    assert all(pot.eligible_players == ("Bob", "Charlie") for pot in hand.pot_results)
    assert hand.payouts == {"Charlie": 48}
    assert sum(p.stack for p in session.players) == 428


def test_a_big_blind_ante_is_not_returned_when_the_big_blind_calls() -> None:
    # Bob and Charlie are all-in for 14; Alice (Big Blind) calls. Her ante is
    # in the main pot, not in a side pot only she could win back.
    session = make_table([400, 14, 14], BIG_BLIND_ANTE, dealer_index=1)
    deck = stacked_deck(
        hole_cards={
            "Charlie": ("2C", "7D"),
            "Alice": ("AS", "AH"),
            "Bob": ("KS", "KH"),
        },
        board=("2D", "5C", "9H", "JS", "3D"),
        order=("Charlie", "Alice", "Bob"),
    )

    hand = play_hand(
        session,
        scripted_actions([("all_in", None), ("call", None), ("call", None)]),
        deck,
    )

    assert [pot.amount for pot in hand.pot_results] == [52]
    assert hand.payouts == {"Alice": 52}


def test_chips_only_folded_players_put_in_join_the_highest_pot() -> None:
    # Alice and Bob are all-in for 3 and 9; Charlie put in 10 and folded.
    alice = Player(name="Alice", stack=0, total_contribution=3, all_in=True)
    bob = Player(name="Bob", stack=0, total_contribution=9, all_in=True)
    charlie = Player(name="Charlie", stack=990, total_contribution=10, folded=True)

    pots = build_pots([alice, bob, charlie])

    # Charlie's last chip, matched by nobody, joins Bob's side pot.
    assert [pot.amount for pot in pots] == [9, 13]
    assert [pot.eligible_players for pot in pots] == [(alice, bob), (bob,)]
    assert pots[1].contributors == (bob, charlie)


def test_dead_money_goes_into_the_main_pot() -> None:
    alice = Player(name="Alice", stack=0, total_contribution=5, all_in=True)
    bob = Player(name="Bob", stack=100, total_contribution=20)

    pots = build_pots([alice, bob], dead_money=10)

    assert [pot.amount for pot in pots] == [20, 15]
    assert pots[0].eligible_players == (alice, bob)
