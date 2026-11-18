"""The Guide window: the application, the bot styles and the poker terms."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from backend.application.profile import ProfileStore
from backend.bots.factory import BOT_TYPES
from frontend.guide import BOT_GUIDES, MAX_LEVEL, SECTIONS, TRAITS
from frontend.ui import guide_window
from frontend.ui.arena_setup_screen import ArenaSetupScreen
from frontend.ui.guide_window import GuidePage, close_guide, meter, open_guide
from frontend.ui.main_window import MainWindow
from frontend.ui.tournament_setup_screen import SpinSetupScreen, TournamentSetupScreen
from tests.frontend.windows import cash_setup, open_table, played_setup


@pytest.fixture
def window(qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    window = MainWindow(save_sessions=False, profile=ProfileStore(tmp_path / "p.json"))
    yield window
    window.close()


def test_every_bot_has_a_guide_entry() -> None:
    assert set(BOT_GUIDES) == set(BOT_TYPES)

    for guide in BOT_GUIDES.values():
        assert len(guide.traits) == len(TRAITS)
        assert all(1 <= level <= MAX_LEVEL for level in guide.traits)
        assert guide.portrait.endswith(".") and guide.how_to_beat.endswith(".")


def test_the_meters_reflect_the_styles() -> None:
    hands, aggression, bluffs, calls, strength = range(len(TRAITS))
    nit, station, maniac = (
        BOT_GUIDES["nit"],
        BOT_GUIDES["station"],
        BOT_GUIDES["maniac"],
    )

    assert nit.traits[hands] < BOT_GUIDES["tag"].traits[hands] < maniac.traits[hands]
    assert station.traits[calls] == MAX_LEVEL and station.traits[aggression] == 1
    assert maniac.traits[bluffs] == MAX_LEVEL
    assert (
        max(g.traits[strength] for g in BOT_GUIDES.values())
        == (BOT_GUIDES["shark"].traits[strength])
    )
    assert meter(2).startswith("●●<span") and meter(2).endswith(">●●●</span>")


def test_the_guide_has_a_page_per_section(qapp: QApplication) -> None:
    guide = open_guide()

    assert guide.current_section == "welcome"
    assert guide.navigation.count() == len(SECTIONS)

    for section in SECTIONS:
        guide.show_section(section.key)
        assert guide.current_section == section.key

    page = guide.page_by_key["bots"]
    assert isinstance(page, GuidePage)
    assert [card.key for card in page.bot_cards] == list(BOT_TYPES)


def test_there_is_only_one_guide_window(qapp: QApplication) -> None:
    first = open_guide("terms")
    second = open_guide("bots", bot="shark")

    assert first is second
    assert second.current_section == "bots"
    assert second.isVisible()

    close_guide()
    assert guide_window._window is None


def test_the_main_menu_opens_the_guide(window: MainWindow) -> None:
    window.main_menu.guide_button.click()

    guide = guide_window._window
    assert guide is not None and guide.isVisible()
    assert guide.current_section == "welcome"


@pytest.mark.parametrize("mode", ["cash", "tournament"])
def test_the_bot_pickers_explain_the_styles(window: MainWindow, mode: str) -> None:
    table = open_table(window, mode)
    if mode == "cash":
        cash_setup(table).bot_picker.help_button.click()
    else:
        setup = played_setup(table)
        assert isinstance(setup, TournamentSetupScreen)
        setup.help_button.click()

    guide = guide_window._window
    assert guide is not None and guide.current_section == "bots"


def test_the_spin_and_go_bots_explain_the_styles(qapp: QApplication) -> None:
    screen = SpinSetupScreen()
    screen.help_button.click()

    guide = guide_window._window
    assert guide is not None and guide.current_section == "bots"


def test_an_arena_seat_explains_its_style(qapp: QApplication) -> None:
    screen = ArenaSetupScreen()
    row = screen.seat_rows[0]
    row.help_button.click()

    guide = guide_window._window
    assert guide is not None and guide.current_section == "bots"


def test_quitting_closes_the_guide(window: MainWindow) -> None:
    window.main_menu.guide_button.click()
    window.close()

    assert guide_window._window is None
