"""V3.0 cash games: buy-in limits, bots rebuying, the straddle in records."""

import random

from backend.application.cash_rules import BuyInRange
from backend.application.controllers import PlayerController
from backend.application.game import PokerGame
from backend.application.game_modes import GameMode
from backend.application.hand_records import live_session_record
from backend.application.replay import HandReplay
from backend.application.setup import GameSettings, create_game
from backend.bots.basic_bot import BasicBot
from backend.poker_engine.session import GameConfig, create_session
from backend.simulation.my_stats import compute_my_stats
from tests.session_files import HUMAN


def test_a_seat_is_bought_for_40_to_100_big_blinds() -> None:
    limits = BuyInRange.for_big_blind(20)

    assert (limits.minimum, limits.maximum) == (800, 2000)
    assert limits.clamp(5000) == 2000 and limits.clamp(100) == 800
    assert limits.top_up(1500) == 500
    assert limits.top_up(2600) == 0  # Never above the maximum.


def bot_game(bots_rebuy: bool) -> PokerGame:
    names = ["Alice", "Bob", "Carol"]
    session = create_session(names, GameConfig(starting_stack=1000))
    session.table.dealer_index = 0
    controllers: dict[str, PlayerController] = {
        name: BasicBot(random.Random(index)) for index, name in enumerate(names)
    }

    return PokerGame(session, controllers, bots_rebuy=bots_rebuy)


def finish_with(game: PokerGame, stacks: dict[str, int]) -> None:
    """Play one hand by folding to the big blind, then set the stacks."""
    hand = game.start_hand()

    for player in game.session.players:
        player.stack = stacks.get(player.name, player.stack)

    hand.finished = True
    game._on_hand_finished()  # noqa: SLF001 - the end of the hand, at once


def test_busted_bots_rebuy_and_short_bots_top_up() -> None:
    game = bot_game(bots_rebuy=True)

    finish_with(game, {"Alice": 0, "Bob": 150, "Carol": 2500})
    alice, bob, carol = game.session.players

    assert (alice.stack, bob.stack, carol.stack) == (1000, 1000, 2500)
    assert not alice.is_eliminated
    assert [(r.player, r.amount, r.rebuy) for r in game.refills] == [
        ("Alice", 1000, True),
        ("Bob", 850, False),
    ]


def test_without_rebuys_busted_bots_leave() -> None:
    game = bot_game(bots_rebuy=False)

    finish_with(game, {"Alice": 0, "Bob": 150})

    assert game.session.players[0].is_eliminated
    assert game.session.players[1].stack == 150
    assert game.refills == []


def test_the_settings_reach_the_game() -> None:
    game = create_game(
        GameSettings(straddle=True, bots_rebuy=False),
        human_controller=BasicBot(random.Random(1)),
        rng=random.Random(1),
    )

    assert game.session.config.straddle
    assert not game.bots_rebuy
    assert game.buy_in_range == BuyInRange(400, 1000)


def test_a_straddled_game_replays_and_its_straddle_is_no_vpip() -> None:
    random.seed(3)
    game = create_game(
        GameSettings(
            player_name=HUMAN, opponents=("tag", "lag", "station"), straddle=True
        ),
        human_controller=BasicBot(random.Random(3)),
        rng=random.Random(3),
    )

    for _ in range(12):
        game.start_hand()
        while game.is_hand_in_progress:
            game.step()

    record = live_session_record(game.session, HUMAN, GameMode.CASH)
    straddled = [
        hand
        for hand in record.hands
        if any(e.action == "post_straddle" for e in hand.actions)
    ]
    assert straddled

    for hand in straddled:
        replay = HandReplay(hand)  # Raises if the deal or the end differ.
        assert replay.step_count > 0

    stats = compute_my_stats([record])
    assert stats.tendencies.vpip is not None and stats.tendencies.vpip < 1.0
