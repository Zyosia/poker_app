"""Multi-table tournaments (V3.1): seating, breaking and balancing tables,
the final table, results, leaving once out, and the settings."""

import random
from collections import Counter
from pathlib import Path

import pytest

from backend.application.controllers import HumanController, PlayerController
from backend.application.game_modes import GameMode
from backend.application.hand_records import load_session_record
from backend.application.payouts import default_payout, field_payout
from backend.application.persistence import save_session
from backend.application.setup import (
    BOT_NAMES,
    TournamentSettings,
    bot_names,
    create_tournament,
)
from backend.application.structures import TURBO
from backend.application.tournament import (
    MAX_ENTRANTS,
    Tournament,
    TournamentConfig,
)
from backend.bots.factory import Difficulty, create_bot, random_styles
from backend.poker_engine.models import Hand
from tests.application.test_tournament import STYLES, Policy


def mtt(
    entrants: int,
    table_size: int,
    final_table_size: int,
    controllers: dict[str, PlayerController] | None = None,
    seed: int = 1,
) -> Tournament:
    names = [f"P{index}" for index in range(entrants)]
    rng = random.Random(seed)
    controllers = controllers or {
        name: create_bot(rng.choice(STYLES), random.Random(rng.getrandbits(64)))
        for name in names
    }
    config = TournamentConfig(
        TURBO, 1500, table_size=table_size, final_table_size=final_table_size
    )

    return Tournament(
        config,
        names,
        controllers,
        deck_rng=random.Random(seed),
        featured="P0",
    )


def seated(tournament: Tournament) -> dict[int, list[str]]:
    """The players still in, by table number."""
    return {
        table.number: [p.name for p in table.session.players if not p.is_eliminated]
        for table in tournament.tables
    }


def knock_out(tournament: Tournament, names: list[str]) -> None:
    """Put players out as if they had busted (their chips are not needed)."""
    first_place = len(tournament.players_left()) - len(names) + 1

    for place, name in enumerate(names, start=first_place):
        player = tournament.player(name)
        player.stack = 0
        player.eliminated = True
        tournament._entries[name].place = place  # noqa: SLF001


# --- Seating -----------------------------------------------------------------


def test_a_field_bigger_than_the_final_table_starts_on_several_tables() -> None:
    tournament = mtt(20, table_size=6, final_table_size=6)

    assert tournament.multi_table
    assert [len(t.session.players) for t in tournament.tables] == [5, 5, 5, 5]
    assert [t.number for t in tournament.tables] == [1, 2, 3, 4]
    table = tournament.table_of("P0")
    assert table is not None and table.number == 1
    assert tournament.session is tournament.tables[0].session


def test_a_field_that_fits_at_the_final_table_plays_one_table() -> None:
    tournament = mtt(8, table_size=6, final_table_size=8)

    assert not tournament.multi_table
    assert len(tournament.tables) == 1
    assert tournament.players == tournament.session.players


def test_tables_must_seat_three_players_and_the_final_table_as_many() -> None:
    with pytest.raises(ValueError):
        TournamentConfig(TURBO, 1500, table_size=2)

    with pytest.raises(ValueError):
        TournamentConfig(TURBO, 1500, table_size=8, final_table_size=6)


def test_only_the_featured_player_may_be_human_on_several_tables() -> None:
    names = [f"P{index}" for index in range(12)]
    controllers: dict[str, PlayerController] = {name: Policy() for name in names}
    controllers["P5"] = Policy(is_human=True)
    config = TournamentConfig(TURBO, 1500, table_size=6, final_table_size=6)

    with pytest.raises(ValueError, match="human"):
        Tournament(config, names, controllers, featured="P0")


# --- Breaking and balancing ----------------------------------------------------


def test_the_player_moved_to_balance_is_the_next_big_blind() -> None:
    tournament = mtt(12, table_size=4, final_table_size=4)
    tournament.play_hand()
    knock_out(tournament, seated(tournament)[3][:2])
    table_two = tournament.tables[1].session.table
    clockwise = table_two.players_after(table_two.dealer)

    tournament._arrange_tables()  # noqa: SLF001 - before the next round

    [move] = tournament.table_moves
    # The next hand: clockwise[0] takes the button, [1] and [2] the blinds.
    assert (move.name, move.from_table, move.to_table) == (clockwise[2].name, 2, 3)
    assert sorted(len(names) for names in seated(tournament).values()) == [3, 3, 4]


def test_the_featured_player_is_never_moved() -> None:
    tournament = mtt(12, table_size=4, final_table_size=4)
    tournament.play_hand()
    table_one = tournament.tables[0].session
    # P0 would be the next big blind at table 1: two seats after the button.
    table_one.table.dealer_index = (
        table_one.players.index(tournament.player("P0")) - 3
    ) % 4
    knock_out(tournament, seated(tournament)[2][:1] + seated(tournament)[3][:2])

    tournament._arrange_tables()  # noqa: SLF001

    assert all(move.name != "P0" for move in tournament.table_moves)
    assert any(move.from_table == 1 for move in tournament.table_moves)
    table = tournament.table_of("P0")
    assert table is not None and table.number == 1


def test_tables_break_from_the_last_then_gather_at_the_final_table() -> None:
    tournament = mtt(12, table_size=4, final_table_size=6)
    tournament.play_hand()

    knock_out(tournament, ["P1", "P4", "P7", "P10"])  # 8 left: two tables.
    tournament._arrange_tables()  # noqa: SLF001

    assert [table.number for table in tournament.tables] == [1, 2]
    assert sorted(len(names) for names in seated(tournament).values()) == [4, 4]
    assert {move.from_table for move in tournament.table_moves} == {3}
    assert tournament.final_table_hand is None

    knock_out(tournament, seated(tournament)[2][:2])  # 6 left: the final table.
    tournament._arrange_tables()  # noqa: SLF001

    assert [table.number for table in tournament.tables] == [1]
    assert len(seated(tournament)[1]) == 6
    assert tournament.final_table_hand == tournament.hands_played + 1


def check_tables(tournament: Tournament, hand: Hand) -> None:
    """At every hand: tables within one player of each other, never above
    their size, and the featured player at table 1 while in."""
    del hand
    sizes = [len(names) for names in seated(tournament).values()]
    config = tournament.config

    if len(sizes) == 1:
        assert sizes[0] <= config.final_table_size
    else:
        assert max(sizes) - min(sizes) <= 1
        assert max(sizes) <= config.table_size

    table = tournament.table_of("P0")

    if not tournament.player("P0").is_eliminated:
        assert table is not None and table.number == 1


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_complete_multi_table_tournaments_conserve_chips_and_pay_the_pool(
    seed: int,
) -> None:
    tournament = mtt(40, table_size=6, final_table_size=8, seed=seed)
    tournament.on_hand_end = lambda hand, stacks: check_tables(tournament, hand)
    chips = 40 * 1500

    while not tournament.is_finished:
        tournament.play_round()
        assert sum(player.stack for player in tournament.players) == chips

    result = tournament.result
    assert sum(finish.prize for finish in result.finishes) == result.prize_pool
    assert result.winner.place == 1
    assert [t.number for t in tournament.tables] == [1]
    assert tournament.final_table_hand is not None

    # Places in competition order: players sharing a place cover the next ones.
    counts = Counter(finish.place for finish in result.finishes)
    place = 1

    while place <= 40:
        assert place in counts
        place += counts[place]


def test_the_same_seed_gives_the_same_multi_table_tournament() -> None:
    first = mtt(30, table_size=6, final_table_size=6, seed=7).play_to_end()
    second = mtt(30, table_size=6, final_table_size=6, seed=7).play_to_end()

    assert first == second


# --- Leaving once out -----------------------------------------------------------


def test_once_out_the_prize_and_the_standings_are_known(tmp_path: Path) -> None:
    names = [f"P{index}" for index in range(20)]
    rng = random.Random(4)
    controllers: dict[str, PlayerController] = {
        name: create_bot(rng.choice(STYLES), random.Random(index))
        for index, name in enumerate(names)
    }
    controllers["P0"] = Policy("fold")  # Blinded out, early.
    tournament = mtt(20, table_size=6, final_table_size=6, controllers=controllers)

    assert tournament.known_prize("P0") is None

    while not tournament.player("P0").is_eliminated:
        tournament.play_round()

    assert not tournament.is_finished
    place = tournament.current_place("P0")
    assert tournament.known_prize("P0") == tournament.prize_for_place(place)

    standings = tournament.standings()
    finishes = standings["finishes"]
    assert isinstance(finishes, list) and len(finishes) == 20
    assert standings["unfinished"] is True
    path = save_session(
        tournament.session,
        tmp_path / "left.json",
        tournament=standings,
        human="P0",
        mode=GameMode.TOURNAMENT,
    )
    finish = load_session_record(path).finish
    assert finish is not None
    assert (finish.place, finish.entrants) == (place, 20)


# --- Payouts ----------------------------------------------------------------------


def test_a_large_field_pays_about_15_percent_of_the_entrants() -> None:
    payout = default_payout(44)

    assert payout.places_paid == 7
    assert sum(payout.percentages) == payout.scale == 10_000
    assert list(payout.percentages) == sorted(payout.percentages, reverse=True)
    assert sum(payout.prizes(44_000, 44)) == 44_000


def test_the_last_paid_place_wins_more_than_its_buy_in() -> None:
    prizes = default_payout(500).prizes(500 * 1_000, 500)
    paid = [prize for prize in prizes if prize]

    assert len(paid) == 75
    assert paid[-1] > 1_000
    assert field_payout(3).percentages == (5455, 2727, 1818)


# --- Settings ---------------------------------------------------------------------


def test_settings_with_a_big_field_seat_you_at_table_1() -> None:
    settings = TournamentSettings(
        opponents=("tag",) * 29, table_size=6, final_table_size=9
    )
    tournament = create_tournament(settings, HumanController(), random.Random(3))

    assert settings.is_multi_table
    assert tournament.multi_table
    assert [len(t.session.players) for t in tournament.tables] == [6] * 5
    table = tournament.table_of(settings.player_name)
    assert table is not None and table.number == 1
    assert tournament.featured == settings.player_name


def test_custom_bot_names_are_used_and_checked() -> None:
    settings = TournamentSettings(opponents=("tag", "nit"), bot_names=("Ann", "Ben"))
    tournament = create_tournament(settings, HumanController(), random.Random(3))

    assert [p.name for p in tournament.players] == ["Hero", "Ann", "Ben"]

    for names in (("Ann", "Ann"), ("Ann", "Hero"), ("Ann", " "), ("Ann",)):
        with pytest.raises(ValueError):
            TournamentSettings(opponents=("tag", "nit"), bot_names=names)

    with pytest.raises(ValueError):
        TournamentSettings(opponents=("tag",) * MAX_ENTRANTS)

    with pytest.raises(ValueError):
        TournamentSettings(table_size=7, final_table_size=6)


def test_bot_names_never_run_out() -> None:
    names = bot_names(MAX_ENTRANTS, {"Alex"})

    assert len(set(names)) == MAX_ENTRANTS
    assert "Alex" not in names
    assert names[:8] == list(BOT_NAMES[1:])
    assert "Bella 2" in names


def test_random_lineups_follow_the_difficulty() -> None:
    easy = random_styles(500, Difficulty.EASY, random.Random(1))
    hard = random_styles(500, Difficulty.HARD, random.Random(1))

    assert not {"shark", "adaptive"} & set(easy)
    strong = sum(style in ("shark", "adaptive") for style in hard)
    assert strong > 200
    assert random_styles(20, Difficulty.NORMAL, random.Random(5)) == random_styles(
        20, Difficulty.NORMAL, random.Random(5)
    )
