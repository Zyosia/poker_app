"""Tournament and Spin & Go played by the user, from the menu to the results."""

import json
import random
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from backend.application.controllers import HumanController
from backend.application.setup import (
    LEVELS_BY_TIME,
    SpinSettings,
    TournamentSettings,
    create_spin_and_go,
)
from backend.application.tournament import Tournament
from backend.poker_engine.actions import Action
from backend.poker_engine.betting import get_legal_actions
from backend.poker_engine.constants import ActionType
from frontend.ui.bot_manager_dialog import FieldBot
from frontend.ui.main_window import MainWindow
from frontend.ui.tournament_results_screen import TournamentResultsScreen
from frontend.ui.tournament_screen import TournamentScreen
from frontend.ui.tournament_setup_screen import SpinSetupScreen, TournamentSetupScreen
from tests.frontend.windows import open_table, tournament_screen

TIMEOUT_SECONDS = 60


BUST_SEED = 15
"""With 3 opponents and 200 chips, the always-all-in human finishes 4th."""


@pytest.fixture
def window(qapp: QApplication) -> Iterator[MainWindow]:
    window = MainWindow(save_sessions=False, rng=random.Random(12))
    yield window
    window.close()


@pytest.fixture
def busting_window(qapp: QApplication) -> Iterator[MainWindow]:
    window = MainWindow(save_sessions=False, rng=random.Random(BUST_SEED))
    yield window
    window.close()


def shown(button: QPushButton) -> bool:
    return not button.isHidden()


def play(
    screen: TournamentScreen,
    until: Callable[[], bool],
    decide: Callable[[TournamentScreen], QPushButton | None],
    plan: ActionType = ActionType.ALL_IN,
) -> None:
    """Drive the table: the human plays ``plan``; ``decide`` picks a button.

    ``decide`` is asked whenever the tournament page (between hands) is
    shown; returning None waits.
    """
    deadline = time.monotonic() + TIMEOUT_SECONDS
    screen.step_delay_ms = 0

    while not until():
        if time.monotonic() > deadline:
            raise AssertionError("The tournament never reached the expected state.")

        game = screen.game

        if screen.is_revealing:
            screen.finish_reveal()
        elif game is not None and game.is_waiting_for_human:
            hand = game.hand
            assert hand is not None and hand.current_player is not None
            legal = {a.type for a in get_legal_actions(hand.current_player, hand)}
            choices = (plan, ActionType.CALL, ActionType.CHECK, ActionType.FOLD)
            action = next(choice for choice in choices if choice in legal)
            screen.action_panel.action_chosen.emit(Action(type=action))
        elif screen.bottom_stack.currentWidget() is screen.tournament_page:
            button = decide(screen)

            if button is not None:
                button.click()

        QTest.qWait(1)


def keep_playing(screen: TournamentScreen) -> QPushButton | None:
    for button in (
        screen.results_button,
        screen.continue_button,
        screen.skip_button,
    ):
        if shown(button):
            return button

    return None


def results_shown(window: MainWindow) -> bool:
    """The results replaced the table, in the game's window."""
    table = window.game_windows[-1]

    return table.current_screen is table.results_screen


def results(window: MainWindow) -> TournamentResultsScreen:
    return window.game_windows[-1].results_screen


def start(window: MainWindow, mode: str, **fields: object) -> TournamentScreen:
    table = open_table(window, mode)
    setup = table.setup_screen

    if isinstance(setup, TournamentSetupScreen):
        setup.opponents_spin.setValue(int(fields.get("opponents", 2)))  # type: ignore[arg-type]
        setup.stack_spin.setValue(int(fields.get("stack", 200)))  # type: ignore[arg-type]
        setup.rebuys_check.setChecked(bool(fields.get("rebuys", False)))

        if fields.get("by_time"):
            setup.speed_combo.setCurrentIndex(
                setup.speed_combo.findData(LEVELS_BY_TIME)
            )

    assert isinstance(setup, TournamentSetupScreen | SpinSetupScreen)
    setup.start_button.click()
    assert table.current_screen is table.table_screen

    return tournament_screen(table)


# --- Menu -----------------------------------------------------------------


def test_the_menu_opens_both_tournament_modes(window: MainWindow) -> None:
    tournament = open_table(window, "tournament")
    assert isinstance(tournament.setup_screen, TournamentSetupScreen)

    tournament.setup_screen.back_button.click()
    assert window.game_windows == []

    spin = open_table(window, "spin")
    assert isinstance(spin.setup_screen, SpinSetupScreen)
    assert window.current_screen is window.main_menu


def test_the_setup_builds_the_settings(window: MainWindow) -> None:
    setup = open_table(window, "tournament").setup_screen
    assert isinstance(setup, TournamentSetupScreen)
    setup.set_field([FieldBot(name, "maniac") for name in ("Ann", "Ben", "Cid")])
    setup.rebuys_check.setChecked(True)

    settings = setup.current_settings()

    assert settings.opponents == ("maniac", "maniac", "maniac")
    assert settings.bot_names == ("Ann", "Ben", "Cid")
    assert settings.rebuys
    assert settings.tournament_config().rebuys is not None

    setup.set_player_name(" ")
    setup.start_button.click()
    assert "name" in setup.error_label.text()


# --- Playing ----------------------------------------------------------------


def test_a_small_tournament_plays_to_the_results(window: MainWindow) -> None:
    screen = start(window, "tournament", opponents=2, stack=200)
    tournament = screen.tournament

    assert "LEVEL 1" in screen.status_label.text()
    assert "players left" in screen.status_label.text()

    play(
        screen,
        until=lambda: results_shown(window),
        decide=keep_playing,
        plan=ActionType.CALL,
    )

    screen_of_results = results(window)
    assert tournament.is_finished
    assert screen_of_results.standings_table.rowCount() == 3
    assert "RESULTS" in screen_of_results.title_label.text()
    assert "Hands played" in screen_of_results.stats_label.text()
    assert sum(f.prize for f in tournament.result.finishes) == tournament.prize_pool

    screen_of_results.menu_button.click()
    table = window.game_windows[-1]
    assert table.current_screen is table.setup_screen


def test_antes_are_posted_and_shown_once_the_levels_rise(window: MainWindow) -> None:
    screen = start(window, "tournament", opponents=2, stack=5000)
    tournament = screen.tournament

    # Turbo: big-blind antes from level 4, after 18 hands.
    play(
        screen,
        until=lambda: tournament.hands_played >= 19 or tournament.is_finished,
        decide=keep_playing,
        plan=ActionType.FOLD,
    )

    assert "posts ante" in screen.history_view.text()


def test_skip_to_results_after_busting(busting_window: MainWindow) -> None:
    window = busting_window
    screen = start(window, "tournament", opponents=3, stack=200)
    tournament = screen.tournament
    name = "Hero"

    def bust_then_skip(screen: TournamentScreen) -> QPushButton | None:
        if shown(screen.skip_button):
            return screen.skip_button

        return keep_playing(screen)

    play(
        screen,
        until=lambda: results_shown(window),
        decide=bust_then_skip,
    )

    finish = tournament.result.finish_of(name)
    assert finish.place > 1, "this seed makes the human bust first"
    assert finish.eliminated_on_hand is not None
    assert tournament.result.winner.name != name
    assert "You finished" in results(window).outcome_label.text()


def test_watching_after_busting_plays_the_rest(busting_window: MainWindow) -> None:
    window = busting_window
    screen = start(window, "tournament", opponents=3, stack=200)

    def bust_then_watch(screen: TournamentScreen) -> QPushButton | None:
        if shown(screen.watch_button):
            return screen.watch_button

        if shown(screen.results_button):
            return screen.results_button

        return None if screen.spectating else keep_playing(screen)

    play(
        screen,
        until=lambda: results_shown(window),
        decide=bust_then_watch,
    )

    assert screen.spectating
    assert results(window).standings_table.rowCount() == 4


def test_a_busted_player_is_offered_a_rebuy(window: MainWindow) -> None:
    screen = start(window, "tournament", opponents=2, stack=200, rebuys=True)
    tournament = screen.tournament

    play(
        screen,
        until=lambda: (
            shown(screen.tournament_rebuy_button)
            and tournament.is_waiting_for_rebuy
            or tournament.is_finished
        ),
        decide=keep_playing,
    )

    assert not tournament.is_finished, "this seed makes the human bust early"
    pool = tournament.prize_pool
    screen.tournament_rebuy_button.click()

    assert tournament.prize_pool == pool + tournament.config.buy_in
    assert tournament.invested("Hero") == 2 * tournament.config.buy_in
    assert not tournament.is_waiting_for_rebuy


def test_pause_freezes_the_level_clock(window: MainWindow) -> None:
    screen = start(window, "tournament", by_time=True)
    clock = screen.tournament.clock
    assert clock is not None and shown(screen.pause_button)

    screen.toggle_pause()
    frozen = clock.elapsed()
    QTest.qWait(30)

    assert clock.is_paused and clock.elapsed() == frozen
    assert "PAUSED" in screen.status_label.text()

    screen.toggle_pause()
    assert not clock.is_paused


# --- Spin & Go --------------------------------------------------------------


def test_a_spin_and_go_reveals_its_multiplier_and_ends_with_a_winner(
    window: MainWindow,
) -> None:
    screen = start(window, "spin")
    tournament = screen.tournament
    multiplier = tournament.multiplier
    assert multiplier is not None

    assert screen.is_revealing
    assert tournament.hand is None  # No card dealt during the reveal.
    screen.finish_reveal()
    assert f"× {multiplier.value}" in screen.history_view.text()

    play(
        screen,
        until=lambda: results_shown(window),
        decide=keep_playing,
    )

    assert f"multiplier × {multiplier.value}" in results(window).outcome_label.text()
    assert tournament.result.winner.prize == tournament.prize_pool


def test_the_reveal_lands_on_the_drawn_multiplier(qapp: QApplication) -> None:
    screen = TournamentScreen()
    tournament = create_spin_and_go(SpinSettings(), HumanController(), random.Random(3))
    screen.start_tournament(tournament, "Hero")
    assert tournament.multiplier is not None

    while screen._reveal_values:  # noqa: SLF001 - run the animation instantly
        screen._reveal_tick()  # noqa: SLF001

    assert f"× {tournament.multiplier.value}" in screen.reveal_label.text()
    assert f"PRIZE POOL {tournament.prize_pool}" in screen.reveal_label.text()
    screen.stop()


def test_a_finished_tournament_is_saved_with_its_results(
    qapp: QApplication, tmp_path: Path
) -> None:
    screen = TournamentScreen()
    tournament = create_spin_and_go(SpinSettings(), HumanController(), random.Random(5))
    path = tmp_path / "spin.dat"
    screen.start_tournament(tournament, "Hero", save_path=path)

    play(screen, until=lambda: tournament.is_finished, decide=keep_playing)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format_version"] == 4
    assert (data["human"], data["mode"]) == ("Hero", "spin")
    assert data["tournament"]["multiplier"] == tournament.result.multiplier
    assert len(data["tournament"]["finishes"]) == 3
    assert data["hands"]
    screen.stop()


def test_tournament_settings_are_validated() -> None:
    with pytest.raises(ValueError):
        TournamentSettings(opponents=())

    with pytest.raises(ValueError):
        TournamentSettings(structure="Glacial")

    with pytest.raises(ValueError):
        SpinSettings(opponents=("tag",))  # type: ignore[arg-type]


def test_tournaments_from_settings_seat_the_human_first() -> None:
    from backend.application.setup import create_tournament

    tournament: Tournament = create_tournament(
        TournamentSettings(opponents=("tag", "lag")),
        HumanController(),
        random.Random(1),
    )

    assert [p.name for p in tournament.players][0] == "Hero"
    assert tournament.keep_hands
