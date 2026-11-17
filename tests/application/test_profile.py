"""The user profile file: defaults, atomic saves and recovery."""

import json
from pathlib import Path

import pytest

from backend.application.profile import (
    PROFILE_FORMAT_VERSION,
    ProfileError,
    ProfileStore,
    UserProfile,
    UserSettings,
)


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "profile.json"


def test_the_first_launch_uses_the_defaults_and_writes_nothing(path: Path) -> None:
    store = ProfileStore(path)

    assert store.profile == UserProfile()
    assert store.settings.show_in_big_blinds is False
    assert store.warning is None
    assert not path.exists()


def test_settings_are_saved_and_read_back(path: Path) -> None:
    store = ProfileStore(path)
    store.settings.show_in_big_blinds = True
    store.save()

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format_version"] == PROFILE_FORMAT_VERSION
    assert ProfileStore(path).settings.show_in_big_blinds is True


def test_a_save_keeps_the_previous_file_as_backup(path: Path) -> None:
    store = ProfileStore(path)
    store.save()
    store.settings.show_in_big_blinds = True
    store.save()

    backup = path.with_suffix(".bak")
    backup_settings = json.loads(backup.read_text(encoding="utf-8"))["settings"]
    assert backup_settings["show_in_big_blinds"] is False
    assert not path.with_suffix(".tmp").exists()


def test_a_damaged_file_is_restored_from_the_backup(path: Path) -> None:
    store = ProfileStore(path)
    store.settings.show_in_big_blinds = True
    store.save()
    store.save()  # The backup now holds the same profile.
    path.write_text("{ not json", encoding="utf-8")

    restored = ProfileStore(path)

    assert restored.settings.show_in_big_blinds is True
    assert restored.warning is not None and "backup" in restored.warning
    damaged = list(path.parent.glob("profile.damaged_*.json"))
    assert len(damaged) == 1, "the damaged file is kept, never deleted"
    assert damaged[0].read_text(encoding="utf-8") == "{ not json"


def test_an_interrupted_save_falls_back_to_the_backup(path: Path) -> None:
    store = ProfileStore(path)
    store.settings.show_in_big_blinds = True
    store.save()
    store.save()
    path.unlink()  # Crash after the backup copy, before the rename.

    restored = ProfileStore(path)

    assert restored.settings.show_in_big_blinds is True
    assert restored.warning is not None


def test_a_damaged_file_without_backup_is_reported_and_kept(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text('{"format_version": 99}', encoding="utf-8")

    store = ProfileStore(path)

    assert store.profile == UserProfile()
    assert store.warning is not None and "version 99" in store.warning
    assert list(path.parent.glob("profile.damaged_*.json"))


def test_an_in_memory_profile_never_touches_the_disk(tmp_path: Path) -> None:
    store = ProfileStore()
    store.settings.show_in_big_blinds = True
    store.save()

    assert store.path is None
    assert list(tmp_path.iterdir()) == []


def test_settings_ignore_unknown_keys_and_reject_wrong_types() -> None:
    settings = UserSettings.from_dict({"show_in_big_blinds": True, "future": 1})
    assert settings.show_in_big_blinds is True

    with pytest.raises(ProfileError):
        UserSettings.from_dict({"show_in_big_blinds": "yes"})
