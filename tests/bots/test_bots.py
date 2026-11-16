import random

import pytest

from backend.application.controllers import (
    DecisionContext,
    PlayerController,
    PlayerView,
)
from backend.application.game import PokerGame
from backend.bots.basic_bot import BasicBot, postflop_strength, preflop_strength
from backend.bots.random_bot import RandomBot
from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.constants import ActionType, Street
from backend.poker_engine.session import GameConfig, create_session

BOT_NAMES = ["Alice", "Bob", "Charlie", "Dave"]
STARTING_STACK = 200


def make_context(
    hole_cards: tuple[str, ...],
    community_cards: tuple[str, ...] = (),
    pot: int = 15,
    to_call: int = 0,
    stack: int = 1000,
) -> DecisionContext:
    """Build the decision of a player facing one opponent."""
    current_bet = max(to_call, 0)
    hero = PlayerView("Hero", stack, 0, 0, None, False, False, True)
    villain = PlayerView(
        "Villain", 1000, current_bet, current_bet, None, False, False, False
    )

    legal_actions = [LegalAction(type=ActionType.FOLD)]

    if to_call:
        legal_actions.append(LegalAction(type=ActionType.CALL, amount=to_call))
    else:
        legal_actions.append(LegalAction(type=ActionType.CHECK))

    legal_actions.append(
        LegalAction(
            type=ActionType.RAISE,
            min_amount=max(2 * current_bet, 10),
            max_amount=stack,
        )
    )
    legal_actions.append(LegalAction(type=ActionType.ALL_IN, amount=stack))

    return DecisionContext(
        player=hero,
        hole_cards=hole_cards,
        community_cards=community_cards,
        pot=pot,
        current_bet=current_bet,
        big_blind=10,
        legal_actions=tuple(legal_actions),
        players=(hero, villain),
        street=Street.PREFLOP if not community_cards else Street.FLOP,
    )


def assert_action_is_legal(action: Action, context: DecisionContext) -> None:
    legal = {legal_action.type: legal_action for legal_action in context.legal_actions}

    assert action.type in legal

    if action.type == ActionType.RAISE:
        raise_action = legal[ActionType.RAISE]
        assert raise_action.min_amount is not None
        assert raise_action.max_amount is not None
        assert action.amount is not None
        assert raise_action.min_amount <= action.amount <= raise_action.max_amount


class LegalityCheckingController(PlayerController):
    """Wraps a bot and verifies every decision against the legal actions."""

    def __init__(self, bot: PlayerController) -> None:
        self.bot = bot
        self.decisions = 0

    def choose_action(self, context: DecisionContext) -> Action:
        action = self.bot.choose_action(context)
        assert_action_is_legal(action, context)
        self.decisions += 1

        return action


def play_session(controllers: dict[str, PlayerController], max_hands: int) -> PokerGame:
    """Play up to ``max_hands`` hands, checking chip conservation throughout."""
    session = create_session(
        list(controllers),
        GameConfig(starting_stack=STARTING_STACK, small_blind=5, big_blind=10),
    )
    session.table.dealer_index = 0
    game = PokerGame(session=session, controllers=controllers)
    total_chips = STARTING_STACK * len(controllers)

    while game.can_start_hand() and session.hand_number < max_hands:
        hand = game.start_hand()

        while game.is_hand_in_progress:
            game.step()
            assert sum(p.stack for p in session.players) + hand.pot == total_chips

        assert hand.pot == 0
        assert all(player.stack >= 0 for player in session.players)

    return game


# ============================================================
# Complete sessions
# ============================================================


@pytest.mark.parametrize("seed", range(20))
def test_random_bots_only_play_legal_actions_and_preserve_chips(seed: int) -> None:
    rng = random.Random(seed)
    controllers: dict[str, PlayerController] = {
        name: LegalityCheckingController(RandomBot(random.Random(rng.random())))
        for name in BOT_NAMES
    }

    game = play_session(controllers, max_hands=40)

    assert game.session.hand_number > 0
    assert sum(p.stack for p in game.session.players) == STARTING_STACK * 4


@pytest.mark.parametrize("seed", range(20))
def test_basic_bots_only_play_legal_actions_and_preserve_chips(seed: int) -> None:
    rng = random.Random(seed)
    controllers: dict[str, PlayerController] = {
        name: LegalityCheckingController(BasicBot(random.Random(rng.random())))
        for name in BOT_NAMES
    }

    game = play_session(controllers, max_hands=40)

    assert game.session.hand_number > 0
    assert sum(p.stack for p in game.session.players) == STARTING_STACK * 4


def test_mixed_bots_can_play_a_session_to_its_end() -> None:
    controllers: dict[str, PlayerController] = {
        "Alice": LegalityCheckingController(RandomBot(random.Random(1))),
        "Bob": LegalityCheckingController(RandomBot(random.Random(2))),
        "Charlie": LegalityCheckingController(BasicBot(random.Random(3))),
    }

    game = play_session(controllers, max_hands=2000)

    remaining = game.session.get_players_with_chips()

    assert len(remaining) == 1
    assert remaining[0].stack == STARTING_STACK * 3


# ============================================================
# RandomBot
# ============================================================


def test_random_bot_is_deterministic_for_a_given_seed() -> None:
    context = make_context(("AS", "KH"), to_call=10)

    first = [RandomBot(random.Random(5)).choose_action(context) for _ in range(3)]
    second = [RandomBot(random.Random(5)).choose_action(context) for _ in range(3)]

    assert first == second


def test_random_bot_eventually_uses_every_legal_action() -> None:
    context = make_context(("AS", "KH"), to_call=10)
    bot = RandomBot(random.Random(0))

    chosen_types = {bot.choose_action(context).type for _ in range(200)}

    assert chosen_types == {action.type for action in context.legal_actions}


# ============================================================
# BasicBot
# ============================================================


def test_preflop_strength_ranks_premium_hands_above_weak_hands() -> None:
    assert preflop_strength(("AS", "AH")) == 1.0
    assert preflop_strength(("AS", "KS")) > preflop_strength(("AS", "KH"))
    assert preflop_strength(("KS", "KH")) > preflop_strength(("9S", "9H"))
    assert preflop_strength(("9S", "9H")) > preflop_strength(("TS", "4H"))
    assert preflop_strength(("7S", "2H")) == 0.0


def test_postflop_strength_ranks_made_hands_above_draws_and_air() -> None:
    board = ("KS", "8H", "3D")

    trips = postflop_strength(("8S", "8D"), board)
    top_pair = postflop_strength(("KH", "QD"), board)
    low_pair = postflop_strength(("3S", "QD"), board)
    air = postflop_strength(("7C", "2C"), board)

    assert trips > top_pair > low_pair > air


def test_postflop_strength_gives_no_credit_for_a_pair_on_the_board() -> None:
    assert postflop_strength(("7C", "2D"), ("KS", "KH", "3D")) < 0.3


def test_postflop_strength_values_a_flush_draw() -> None:
    board = ("KS", "8S", "3D")

    assert postflop_strength(("AS", "2S"), board) > postflop_strength(
        ("AC", "2H"), board
    )


def test_basic_bot_raises_with_a_premium_hand() -> None:
    context = make_context(("AS", "AH"), to_call=10)

    action = BasicBot(random.Random(0)).choose_action(context)

    assert action.type == ActionType.RAISE
    assert_action_is_legal(action, context)


def test_basic_bot_folds_a_weak_hand_to_a_large_bet() -> None:
    context = make_context(("7S", "2H"), pot=300, to_call=200)

    action = BasicBot(random.Random(0)).choose_action(context)

    assert action == Action(type=ActionType.FOLD)


def test_basic_bot_never_folds_when_it_can_check() -> None:
    context = make_context(("7S", "2H"), ("KD", "QC", "9H"), pot=40)

    for seed in range(50):
        action = BasicBot(random.Random(seed)).choose_action(context)

        assert action.type != ActionType.FOLD
        assert_action_is_legal(action, context)


def test_basic_bot_calls_a_small_bet_with_a_good_hand() -> None:
    context = make_context(("KH", "QD"), ("KS", "8H", "3D"), pot=100, to_call=60)

    action = BasicBot(random.Random(0)).choose_action(context)

    assert action == Action(type=ActionType.CALL)


def test_basic_bot_goes_all_in_when_strong_and_unable_to_raise() -> None:
    context = make_context(("8S", "8D"), ("KS", "8H", "3D"), pot=100, to_call=20)
    legal_actions = tuple(
        action for action in context.legal_actions if action.type != ActionType.RAISE
    )
    context = DecisionContext(
        player=context.player,
        hole_cards=context.hole_cards,
        community_cards=context.community_cards,
        pot=context.pot,
        current_bet=context.current_bet,
        big_blind=context.big_blind,
        legal_actions=legal_actions,
        players=context.players,
        street=context.street,
    )

    action = BasicBot(random.Random(0)).choose_action(context)

    assert action == Action(type=ActionType.ALL_IN)
