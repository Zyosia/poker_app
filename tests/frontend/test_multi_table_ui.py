"""Multi-table tournaments in the interface (V3.1): the bots of the setup and
their manager, the lobby window, your table, and leaving once out."""

import random
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from backend.application.bankroll import TransactionType
from backend.application.profile import ProfileStore
from backend.bots.factory import DIFFICULTY_WEIGHTS, Difficulty
from frontend.ui.bot_manager_dialog import BotManagerDialog, FieldBot, describe_field
from frontend.ui.main_window import MainWindow
from frontend.ui.tournament_screen import TournamentScreen
from frontend.ui.tournament_setup_screen import TournamentSetupScreen
from tests.frontend.test_tournament_mode import keep_playing, play, results_shown, shown
from tests.frontend.windows import open_table, tournament_screen

STRONG = {"shark", "adaptive"}


@pytest.fixture
def window(qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    window = MainWindow(
        save_sessions=False,
        rng=random.Random(15),
        profile=ProfileStore(tmp_path / "profile.json"),
    )
    yield window
    window.close()


def easy(setup: TournamentSetupScreen) -> None:
    setup.difficulty_combo.setCurrentIndex(
        setup.difficulty_combo.findData(Difficulty.EASY)
    )


# --- Setup ---------------------------------------------------------------------


def test_more_bots_are_drawn_at_random_for_the_difficulty(qapp: QApplication) -> None:
    setup = TournamentSetupScreen()
    setup.rng.seed(1)
    first_five = list(setup.field)
    easy(setup)

    setup.opponents_spin.setValue(40)

    assert len(setup.field) == 40
    assert setup.field[:5] == first_five
    assert not STRONG & {bot.style for bot in setup.field[5:]}
    assert len({bot.name for bot in setup.field}) == 40
    assert setup.field_label.text() == describe_field(setup.field)

    setup.opponents_spin.setValue(12)

    assert setup.field[:5] == first_five and len(setup.field) == 12


def test_drawing_at_random_restyles_every_bot(qapp: QApplication) -> None:
    setup = TournamentSetupScreen()
    setup.rng.seed(2)
    setup.difficulty_combo.setCurrentIndex(
        setup.difficulty_combo.findData(Difficulty.HARD)
    )
    setup.opponents_spin.setValue(30)

    setup.draw_field()

    styles = {bot.style for bot in setup.field}
    assert len(setup.field) == 30
    assert styles <= set(DIFFICULTY_WEIGHTS[Difficulty.HARD])
    assert STRONG & styles


def test_the_seating_is_described_and_reaches_the_settings(qapp: QApplication) -> None:
    setup = TournamentSetupScreen()
    setup.opponents_spin.setValue(20)
    setup.table_size_spin.setValue(6)
    setup.final_table_spin.setValue(8)

    assert setup.tables_label.text() == (
        "21 players: 4 tables of up to 6, then a final table of 8."
    )
    settings = setup.current_settings()
    assert (settings.table_size, settings.final_table_size) == (6, 8)
    assert settings.bot_names == tuple(bot.name for bot in setup.field)
    assert settings.is_multi_table

    setup.table_size_spin.setValue(9)  # The final table follows.
    assert setup.final_table_spin.value() == 9


def test_your_name_never_goes_to_a_bot(qapp: QApplication) -> None:
    setup = TournamentSetupScreen()
    taken = setup.field[0].name

    setup.set_player_name(taken)

    assert taken not in {bot.name for bot in setup.field}
    assert setup.current_settings().player_name == taken


# --- The bot manager ---------------------------------------------------------------


def test_the_bot_manager_draws_adds_restyles_and_removes(qapp: QApplication) -> None:
    dialog = BotManagerDialog(
        [FieldBot("Ann", "tag")], "Hero", Difficulty.EASY, random.Random(3)
    )
    dialog.count_spin.setValue(25)

    dialog.draw()

    assert len(dialog.field()) == 25
    assert not STRONG & {bot.style for bot in dialog.field()}

    dialog.style_combo.setCurrentIndex(dialog.style_combo.findData("shark"))
    dialog.add_spin.setValue(3)
    dialog.add_button.click()

    assert [bot.style for bot in dialog.field()[-3:]] == ["shark"] * 3

    dialog.table.selectRow(0)
    dialog.style_combo.setCurrentIndex(dialog.style_combo.findData("nit"))
    dialog.restyle_button.click()
    assert dialog.field()[0].style == "nit"

    dialog.table.selectRow(1)
    dialog.remove_button.click()
    assert len(dialog.field()) == 27
    assert "27 bots" in dialog.summary_label.text()


def test_the_bot_manager_refuses_duplicate_names(qapp: QApplication) -> None:
    dialog = BotManagerDialog([FieldBot("Ann", "tag"), FieldBot("Ben", "nit")], "Hero")
    item = dialog.table.item(1, 0)
    assert item is not None
    item.setText("Ann")

    dialog.accept()

    assert "same name" in dialog.error_label.text()
    assert dialog.result() != BotManagerDialog.DialogCode.Accepted


# --- Playing ------------------------------------------------------------------------


def start_multi_table(window: MainWindow) -> TournamentScreen:
    """21 players on tables of 6 (4 tables), a final table of 6."""
    table = open_table(window, "tournament")
    setup = table.setup_screen
    assert isinstance(setup, TournamentSetupScreen)
    setup.rng.seed(4)
    easy(setup)
    setup.opponents_spin.setValue(20)
    setup.table_size_spin.setValue(6)
    setup.final_table_spin.setValue(6)
    setup.stack_spin.setValue(200)
    setup.start_button.click()

    return tournament_screen(table)


def test_a_multi_table_tournament_opens_its_lobby(window: MainWindow) -> None:
    screen = start_multi_table(window)
    table = window.game_windows[-1]
    lobby = table.lobby_window
    tournament = screen.tournament

    assert tournament.multi_table and len(tournament.tables) == 4
    assert lobby is not None and lobby.isVisible()
    assert lobby.players_table.rowCount() == 21
    assert lobby.tables_table.rowCount() == 4
    assert lobby.payouts_table.rowCount() == 3
    assert "TABLE 1 of 4" in screen.status_label.text()
    assert shown(screen.lobby_button)

    # The players are sorted by stack; the search hides the others.
    name = tournament.players[5].name
    lobby.search_edit.setText(name)
    visible = [
        row
        for row in range(lobby.players_table.rowCount())
        if not lobby.players_table.isRowHidden(row)
    ]
    assert len(visible) >= 1

    lobby.close()
    screen.lobby_button.click()
    assert lobby.isVisible()


def test_once_out_skip_to_results_plays_the_rest(window: MainWindow) -> None:
    screen = start_multi_table(window)

    play(screen, lambda: shown(screen.skip_button), keep_playing)
    screen.skip_button.click()
    play(screen, lambda: results_shown(window), lambda s: None)

    results = window.game_windows[-1].results_screen
    assert results.standings_table.rowCount() == 21
    assert screen.tournament.is_finished


def test_leaving_once_out_keeps_your_place(window: MainWindow) -> None:
    screen = start_multi_table(window)
    table = window.game_windows[-1]

    play(screen, lambda: shown(screen.skip_button), keep_playing)
    tournament = screen.tournament
    assert not tournament.is_finished

    screen.leave_button.click()

    assert table.current_screen is table.setup_screen
    assert not tournament.is_finished  # The rest was not played.
    kinds = [t.type for t in window.profile.bankroll.transactions]
    assert TransactionType.FORFEIT not in kinds
    assert window.profile.bankroll.open_games == []
