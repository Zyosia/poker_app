"""Live tables (V3.1.1): the other tables play at their own pace.

The application steps them (``step_table``) while your table plays. They
only wait for one another hand-for-hand, one player away from the money or
from the final table, and your table waits for them before the final table.
Every test here drives the tables in a fixed order: the results are
deterministic.
"""

import random
from collections import Counter

import pytest

from backend.application.setup import TournamentSettings, create_tournament
from backend.application.tournament import Tournament
from backend.bots.factory import create_bot

STACK = 1500
STYLES = ("tag", "lag", "nit", "station", "maniac")


def live_tournament(
    bots: int = 24, table_size: int = 6, final_table_size: int = 9, seed: int = 1
) -> Tournament:
    """You (played by a TAG bot) against ``bots`` bots, on several tables."""
    rng = random.Random(seed)
    settings = TournamentSettings(
        opponents=tuple(rng.choice(STYLES) for _ in range(bots)),
        table_size=table_size,
        final_table_size=final_table_size,
        starting_stack=STACK,
    )
    hero = create_bot("tag", random.Random(seed))

    return create_tournament(settings, hero, random.Random(seed))  # type: ignore[arg-type]


def step_featured(tournament: Tournament) -> None:
    if tournament.is_hand_in_progress:
        tournament.step()
    elif tournament.ready_to_deal():
        tournament.start_hand()


def play_live(tournament: Tournament, others_per_featured: int = 3) -> list[str]:
    """Step every table in turn until the end; return what was observed."""
    seen: list[str] = []
    rounds = 0

    while not tournament.is_finished:
        rounds += 1
        assert rounds < 200_000, "the tournament never ends"
        step_featured(tournament)

        for _ in range(others_per_featured):
            for table in list(tournament.tables[1:]):
                tournament.step_table(table)

        if tournament.hand_for_hand:
            seen.append("hand-for-hand")

        if tournament.final_table_forming:
            seen.append("final table forming")

    return seen


def idle(tournament: Tournament) -> bool:
    return not any(table.is_hand_in_progress for table in tournament.tables)


# --- Setup --------------------------------------------------------------------


def test_only_several_tables_play_live() -> None:
    assert live_tournament(bots=24).live

    one_table = TournamentSettings(opponents=("tag",) * 5)
    hero = create_bot("tag", random.Random(1))
    tournament = create_tournament(one_table, hero, random.Random(1))  # type: ignore[arg-type]

    assert not tournament.multi_table
    assert not tournament.live


def test_only_the_other_tables_are_stepped() -> None:
    tournament = live_tournament()

    with pytest.raises(RuntimeError):
        tournament.step_table(tournament.tables[0])


# --- Playing at their own pace ------------------------------------------------------


def test_the_other_tables_do_not_wait_for_your_hand() -> None:
    tournament = live_tournament()
    tournament.start_hand()
    other = tournament.tables[1]

    while other.hands_played < 3:
        tournament.step_table(other)

    assert tournament.is_hand_in_progress  # Your first hand is not over.
    assert tournament.hands_played == 0
    assert other.hands_played == 3


def test_a_complete_live_tournament_pays_every_place() -> None:
    tournament = live_tournament(bots=30, seed=2)
    seen = play_live(tournament)
    result = tournament.result

    assert "hand-for-hand" in seen
    assert tournament.final_table_hand is not None
    assert len(tournament.tables) == 1
    assert len(result.finishes) == 31
    assert sum(finish.prize for finish in result.finishes) == tournament.prize_pool
    assert tournament.player(result.winner.name).stack == 31 * STACK
    assert sorted(f.place for f in result.finishes)[0] == 1


@pytest.mark.parametrize("seed", [3, 4, 5])
def test_the_chips_and_the_seats_stay_right_between_hands(seed: int) -> None:
    tournament = live_tournament(bots=40, table_size=8, seed=seed)
    total = 41 * STACK
    rounds = 0

    while not tournament.is_finished:
        rounds += 1
        step_featured(tournament)

        for table in list(tournament.tables[1:]):
            tournament.step_table(table)

        if idle(tournament) and not tournament.is_finished:
            assert sum(p.stack for p in tournament.players) == total
            names = [
                player.name
                for table in tournament.tables
                for player in (*tournament._seated(table), *table.incoming)  # noqa: SLF001
            ]
            assert max(Counter(names).values()) == 1  # Nobody sits twice.
            assert set(names) == {p.name for p in tournament.players_left()}

    assert rounds > 0


# --- Hand-for-hand and the final table ---------------------------------------------


def test_hand_for_hand_plays_one_hand_per_table_per_round() -> None:
    checked = sum(hand_for_hand_rounds(seed) for seed in range(6, 12))

    assert checked > 0


def hand_for_hand_rounds(seed: int) -> int:
    """Play a tournament; check every hand-for-hand round, and count them."""
    tournament = live_tournament(bots=30, seed=seed)
    checked = 0

    while not tournament.is_finished:
        if tournament.hand_for_hand and not tournament.is_hand_in_progress:
            # Your table waits for the others to finish their hand.
            if any(t.is_hand_in_progress for t in tournament.tables[1:]):
                assert not tournament.ready_to_deal()

            if tournament.ready_to_deal():
                before = {t.number: t.hands_played for t in tournament.tables}
                tournament.start_hand()

                for _ in range(400):  # Far more steps than one hand needs.
                    for table in list(tournament.tables[1:]):
                        tournament.step_table(table)

                for table in tournament.tables[1:]:
                    assert table.hands_played - before.get(table.number, 0) <= 1

                checked += 1
                continue

        step_featured(tournament)

        for table in list(tournament.tables[1:]):
            tournament.step_table(table)

    return checked


def test_your_table_waits_for_the_final_table_to_form() -> None:
    tournament = live_tournament(bots=24, final_table_size=9, seed=7)

    while len(tournament.tables) > 1:
        step_featured(tournament)

        if tournament.final_table_forming and not tournament.is_hand_in_progress:
            assert not tournament.ready_to_deal()

        for table in list(tournament.tables[1:]):
            tournament.step_table(table)

    assert len(tournament.players_left()) <= 9

    while tournament.is_hand_in_progress:
        tournament.step()

    if not tournament.is_finished:
        tournament.start_hand()

    final = tournament.final_table_hand
    assert final is not None and final <= tournament.hands_played + 1


def test_a_moved_player_sits_down_at_the_next_hand() -> None:
    tournament = live_tournament(bots=30, seed=8)

    while not any(table.incoming for table in tournament.tables):
        step_featured(tournament)

        for table in list(tournament.tables[1:]):
            tournament.step_table(table)

    table = next(table for table in tournament.tables if table.incoming)
    moved = table.incoming[0]

    assert tournament.table_of(moved.name) is table
    assert moved not in table.session.players

    while table.incoming and table in tournament.tables:
        if table is tournament.tables[0]:
            step_featured(tournament)
        else:
            tournament.step_table(table)

        for other in list(tournament.tables[1:]):
            if other is not table:
                tournament.step_table(other)

    seated_at = tournament.table_of(moved.name)
    assert seated_at is not None
    assert moved in seated_at.session.players or moved.is_eliminated


# --- Back to rounds ---------------------------------------------------------------------


def test_stop_live_finishes_the_hands_and_plays_the_rest_in_rounds() -> None:
    tournament = live_tournament(bots=30, seed=9)

    for _ in range(300):
        step_featured(tournament)

        for table in list(tournament.tables[1:]):
            tournament.step_table(table)

    tournament.stop_live()

    assert not tournament.live
    assert idle(tournament)
    assert not any(table.incoming for table in tournament.tables)

    result = tournament.play_to_end()

    assert sum(finish.prize for finish in result.finishes) == tournament.prize_pool
    assert tournament.player(result.winner.name).stack == 31 * STACK
