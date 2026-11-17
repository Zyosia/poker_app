"""Full-ring tables (V1.3): cash games and tournaments of up to nine players,
and cash games choosing each bot's play style."""

import random

import pytest

from backend.application.payouts import (
    TOP_THREE,
    TOP_TWO,
    WINNER_TAKES_ALL,
    default_payout,
)
from backend.application.setup import (
    BOT_NAMES,
    GameSettings,
    TournamentSettings,
    create_game,
    create_tournament,
)
from backend.bots.basic_bot import BasicBot
from backend.bots.factory import BOT_TYPES
from backend.bots.random_bot import RandomBot
from backend.bots.short_stack import FULL_RING_RANGE_POSITIONS
from backend.poker_engine.constants import MAX_TABLE_SEATS, Position
from backend.poker_engine.session import GameConfig, create_session

FULL_RING = ("tag", "lag", "station", "maniac", "nit", "basic", "random", "tag")


def test_a_table_seats_up_to_nine_players() -> None:
    assert MAX_TABLE_SEATS == 9
    names = [f"P{index}" for index in range(9)]

    session = create_session(names, GameConfig())
    assert len(session.players) == 9

    with pytest.raises(ValueError, match="Too many players"):
        create_session([*names, "P9"], GameConfig())


def test_there_are_enough_bot_names_whatever_your_name() -> None:
    assert len(set(BOT_NAMES)) == MAX_TABLE_SEATS

    for name in BOT_NAMES:  # Your name taken by a bot name: one is skipped.
        game = create_game(
            GameSettings(player_name=name, opponents=FULL_RING),
            human_controller=BasicBot(random.Random(0)),
            rng=random.Random(0),
        )
        names = [player.name for player in game.session.players]
        assert len(set(names)) == 9 and names[0] == name


# --- Cash game: bot styles ---------------------------------------------------------


def test_a_cash_game_seats_one_bot_of_each_chosen_style() -> None:
    game = create_game(
        GameSettings(opponents=("random", "nit", "maniac")),
        human_controller=BasicBot(random.Random(0)),
        rng=random.Random(1),
    )
    bots = [game.controllers[player.name] for player in game.session.players[1:]]

    assert isinstance(bots[0], RandomBot)
    assert isinstance(bots[1], BasicBot)
    assert bots[1].profile == BOT_TYPES["nit"].profile
    assert isinstance(bots[2], BasicBot)
    assert bots[2].profile == BOT_TYPES["maniac"].profile


@pytest.mark.parametrize(
    ("opponents", "message"),
    [
        ((), "1 to 8"),
        (("tag",) * 9, "1 to 8"),
        (("genius",), "Unknown bot"),
    ],
)
def test_invalid_cash_opponents_are_rejected(
    opponents: tuple[str, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        GameSettings(opponents=opponents)


def test_a_full_ring_cash_game_keeps_every_chip() -> None:
    random.seed(4)  # The engine deals from the global RNG by default.
    game = create_game(
        GameSettings(opponents=FULL_RING),
        human_controller=BasicBot(random.Random(4)),
        rng=random.Random(4),
    )
    total = sum(player.stack for player in game.session.players)
    seen_positions: set[Position] = set()

    for _ in range(60):
        if not game.can_start_hand():
            break

        hand = game.start_hand()
        seen_positions |= {seat.position for seat in hand.seats if seat.position}

        while game.is_hand_in_progress:
            game.step()

        assert sum(player.stack for player in game.session.players) == total

    assert {Position.UTG1, Position.UTG2, Position.LJ} <= seen_positions


# --- Tournaments --------------------------------------------------------------------


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_a_full_ring_tournament_plays_to_the_end(seed: int) -> None:
    """Short stacks shove from the full-ring early seats too (UTG's range)."""
    settings = TournamentSettings(opponents=FULL_RING, starting_stack=500)
    tournament = create_tournament(
        settings, BasicBot(random.Random(seed)), random.Random(seed)
    )

    result = tournament.play_to_end()

    assert len(result.finishes) == 9
    assert sorted(finish.place for finish in result.finishes) == list(range(1, 10))
    assert sum(f.prize for f in result.finishes) == tournament.prize_pool
    assert [f.prize > 0 for f in sorted(result.finishes, key=lambda f: f.place)] == (
        [True] * 3 + [False] * 6
    ), "50 / 30 / 20 at a full ring"


def test_the_early_full_ring_seats_shove_utgs_range() -> None:
    assert FULL_RING_RANGE_POSITIONS == {
        Position.UTG1: Position.UTG,
        Position.UTG2: Position.UTG,
        Position.LJ: Position.UTG,
    }


def test_default_payouts_pay_three_places_at_a_full_ring() -> None:
    assert [default_payout(n) for n in range(2, 10)] == [
        WINNER_TAKES_ALL,
        WINNER_TAKES_ALL,
        TOP_TWO,
        TOP_TWO,
        TOP_TWO,
        TOP_THREE,
        TOP_THREE,
        TOP_THREE,
    ]
