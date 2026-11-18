"""V2.1: imported histories kept, sessions deleted, all data reset."""

import random
from pathlib import Path

import pytest

from backend.application.bankroll import DEFAULT_BALANCE
from backend.application.game_modes import GameMode
from backend.application.hand_records import (
    IMPORTS_FOLDER,
    SessionLibrary,
    live_session_record,
)
from backend.application.persistence import SessionFileError
from backend.application.profile import ProfileStore, UserSettings
from backend.application.setup import GameSettings, create_game
from backend.bots.basic_bot import BasicBot
from backend.simulation.my_stats import compute_my_stats
from tests.hand_history_text import POKERSTARS_FILE, WINAMAX_FILE
from tests.session_files import HUMAN, cash_session


@pytest.fixture
def library(tmp_path: Path) -> SessionLibrary:
    folder = tmp_path / "sessions"
    folder.mkdir()
    cash_session(folder / "pk_sess_20261110_100000.dat", hands=4)
    cash_session(folder / "pk_sess_20261111_100000.dat", hands=4, seed=2)

    return SessionLibrary(folder)


def history(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")

    return path


# --- Imported histories ------------------------------------------------------------


def test_an_imported_history_is_kept_in_the_library(
    library: SessionLibrary, tmp_path: Path
) -> None:
    original = history(tmp_path, "winamax.txt", WINAMAX_FILE)

    imported = library.import_history(original)
    original.unlink()  # The copy does not depend on the original.

    assert imported.source == "Winamax"
    assert imported.path.parent == library.imports_directory
    assert library.imports_directory.name == IMPORTS_FOLDER

    reopened = SessionLibrary(library.directory).scan(include_imports=True)
    assert [s.source for s in reopened.sessions].count("Winamax") == 1


def test_imports_are_not_played_sessions(
    library: SessionLibrary, tmp_path: Path
) -> None:
    library.import_history(history(tmp_path, "winamax.txt", WINAMAX_FILE))

    assert len(library.scan().sessions) == 2  # My stats, the last hand.
    assert len(library.scan(include_imports=True).sessions) == 3


def test_a_history_is_imported_once_and_names_never_clash(
    library: SessionLibrary, tmp_path: Path
) -> None:
    first = history(tmp_path, "hands.txt", WINAMAX_FILE)
    library.import_history(first)
    library.import_history(first)

    other_folder = tmp_path / "other"
    other_folder.mkdir()
    library.import_history(history(other_folder, "hands.txt", POKERSTARS_FILE))

    names = sorted(p.name for p in library.imports_directory.iterdir())
    assert names == ["hands (2).txt", "hands.txt"]


def test_an_unreadable_history_is_not_kept(
    library: SessionLibrary, tmp_path: Path
) -> None:
    with pytest.raises(SessionFileError):
        library.import_history(history(tmp_path, "notes.txt", "Not a hand history."))

    assert not library.imports_directory.exists()


# --- Deleting --------------------------------------------------------------------------


def test_a_deleted_session_leaves_the_library_and_the_stats(
    library: SessionLibrary,
) -> None:
    before = library.scan().sessions
    assert compute_my_stats(before).sessions == 2

    library.delete(before[0])

    after = library.scan().sessions
    assert not before[0].path.exists()
    assert [s.path for s in after] == [before[1].path]
    assert compute_my_stats(after).sessions == 1
    assert compute_my_stats(after).hands < compute_my_stats(before).hands


def test_a_deleted_import_is_gone(library: SessionLibrary, tmp_path: Path) -> None:
    imported = library.import_history(history(tmp_path, "w.txt", WINAMAX_FILE))

    library.delete(imported)

    assert not imported.path.exists()
    assert all(not s.imported for s in library.scan(include_imports=True).sessions)


def test_files_outside_the_library_are_never_deleted(
    library: SessionLibrary, tmp_path: Path
) -> None:
    outside = library.load(cash_session(tmp_path / "elsewhere.dat", hands=2))

    with pytest.raises(ValueError, match="not in the session library"):
        library.delete(outside)

    assert outside.path.exists()


def test_delete_all_empties_the_library(
    library: SessionLibrary, tmp_path: Path
) -> None:
    library.import_history(history(tmp_path, "w.txt", WINAMAX_FILE))

    assert library.delete_all() == 3
    assert library.scan(include_imports=True).sessions == ()


# --- A game being played -----------------------------------------------------------------


def test_a_game_in_progress_can_be_replayed_from_memory() -> None:
    random.seed(4)
    game = create_game(
        GameSettings(player_name=HUMAN, opponents=("basic", "tag")),
        human_controller=BasicBot(random.Random(4)),
        rng=random.Random(4),
    )

    for _ in range(3):
        game.start_hand()
        while game.is_hand_in_progress:
            game.step()

    game.start_hand()  # A fourth hand, not finished yet.
    record = live_session_record(game.session, HUMAN, GameMode.CASH)

    assert record.human == HUMAN and record.mode == GameMode.CASH
    assert len(record.hands) == 4
    assert [hand.finished for hand in record.hands] == [True, True, True, False]
    assert all(hand.replayable for hand in record.hands[:3])


# --- Deleting all data ---------------------------------------------------------------------


def test_reset_data_starts_the_bankroll_and_the_name_again(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profile.json")
    store.settings.player_name = "Nael"
    store.settings.sound_volume = 30
    store.bankroll.set_balance(4_000)
    store.save()
    store.save()  # A backup now holds the old profile.
    assert store.backup_path is not None and store.backup_path.exists()

    store.reset_data()

    reread = ProfileStore(tmp_path / "profile.json")
    assert reread.bankroll.balance == DEFAULT_BALANCE
    assert reread.bankroll.transactions == []
    assert reread.settings.player_name == UserSettings().player_name
    assert reread.settings.sound_volume == 30  # The other settings stay.
    assert not store.backup_path.exists()
