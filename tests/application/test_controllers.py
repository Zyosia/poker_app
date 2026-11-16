import pytest

from backend.application.controllers import (
    DecisionContext,
    HumanController,
    PlayerController,
    PlayerView,
    build_decision_context,
)
from backend.poker_engine.actions import Action
from backend.poker_engine.betting import apply_action, begin_betting_round
from backend.poker_engine.constants import ActionType, Position, Street
from backend.poker_engine.hand import start_hand
from backend.poker_engine.models import Player
from backend.poker_engine.session import GameConfig, create_session


def make_context() -> DecisionContext:
    player = PlayerView(
        name="Alice",
        stack=1000,
        current_bet=10,
        total_contribution=10,
        position=Position.BTN,
        folded=False,
        all_in=False,
        is_current_player=True,
    )

    return DecisionContext(
        player=player,
        hole_cards=("AS", "KH"),
        community_cards=(),
        pot=15,
        current_bet=10,
        big_blind=10,
        legal_actions=(),
        players=(player,),
        street=Street.PREFLOP,
    )


class AlwaysCheckController(PlayerController):
    def choose_action(self, context: DecisionContext) -> Action:
        return Action(type=ActionType.CHECK)


def test_controller_can_receive_decision_context() -> None:
    controller = AlwaysCheckController()

    assert controller.choose_action(make_context()) == Action(type=ActionType.CHECK)


def test_human_controller_returns_the_submitted_action_once() -> None:
    controller = HumanController()

    assert controller.has_pending_action is False

    controller.submit(Action(type=ActionType.RAISE, amount=40))

    assert controller.has_pending_action is True
    assert controller.choose_action(make_context()) == Action(
        type=ActionType.RAISE,
        amount=40,
    )
    assert controller.has_pending_action is False


def test_human_controller_requires_a_submitted_action() -> None:
    controller = HumanController()

    with pytest.raises(RuntimeError):
        controller.choose_action(make_context())


def test_built_context_holds_the_public_actions_of_the_hand() -> None:
    session = create_session(["Alice", "Bob", "Charlie"], GameConfig())
    session.table.dealer_index = 0
    hand = start_hand(session)
    hand.first_to_act = session.players[0]
    begin_betting_round(hand)
    apply_action(hand, Action(type=ActionType.RAISE, amount=30))

    bob = session.players[1]
    context = build_decision_context(hand=hand, player=bob, big_blind=10)

    assert [event.action for event in context.actions] == [
        "post_sb",
        "post_bb",
        "raise",
    ]
    assert context.player.name == "Bob"
    assert context.hole_cards == tuple(bob.hand)


def test_built_context_never_contains_the_opponents_hole_cards() -> None:
    session = create_session(["Alice", "Bob", "Charlie"], GameConfig())
    session.table.dealer_index = 0
    hand = start_hand(session)
    alice = session.players[0]

    context = build_decision_context(hand=hand, player=alice, big_blind=10)
    opponent_cards = {card for p in session.players[1:] for card in p.hand}

    assert not opponent_cards & set(repr(context).replace("'", " ").split())


def test_building_a_context_for_a_player_who_is_not_seated_fails() -> None:
    session = create_session(["Alice", "Bob"], GameConfig())
    session.table.dealer_index = 0
    hand = start_hand(session)

    with pytest.raises(ValueError, match="not seated"):
        build_decision_context(hand=hand, player=Player("Zoe", 100), big_blind=10)
