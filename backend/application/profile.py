"""The user profile: settings and bankroll kept between launches.

The profile is a JSON file with a ``format_version``. It is written to a
temporary file first and then renamed over the previous one, whose last good
version is kept as a backup. A damaged file is never overwritten silently:
the profile is restored from the backup, or the damaged file is kept aside
and the user is told.

The file's location is chosen by the caller (the desktop app uses the OS's
application data folder), so tests use a temporary directory.
"""

import json
import shutil
from dataclasses import dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any

from .bankroll import Bankroll, BankrollDataError

PROFILE_FORMAT_VERSION = 1
PROFILE_FILE_NAME = "profile.json"


class ProfileError(ValueError):
    """The profile file cannot be read: invalid JSON or content."""


@dataclass
class UserSettings:
    """Preferences of the user."""

    show_in_big_blinds: bool = False
    """Show stacks, bets and the pot in big blinds instead of chips."""
    cash_clock: str = ""
    """The action clock the user chose for cash games ("": the default)."""
    tournament_clock: str = ""
    spin_clock: str = ""
    bankroll_hints: bool = True
    table_speed: str = ""
    """The table speed the user picked ("": the default)."""
    auto_next_hand: bool = True
    """Warn (without blocking) when a buy-in is a large share of the bankroll."""

    def to_dict(self) -> dict[str, Any]:
        return {item.name: getattr(self, item.name) for item in fields(self)}

    @classmethod
    def from_dict(cls, data: object) -> "UserSettings":
        """Read the settings; unknown keys are ignored, missing ones default."""
        if not isinstance(data, dict):
            raise ProfileError("The settings are not an object.")

        settings = cls()

        for item in fields(cls):
            if item.name not in data:
                continue

            value = data[item.name]
            expected = type(getattr(settings, item.name))

            if type(value) is not expected:
                raise ProfileError(f"The setting {item.name} has an invalid value.")

            setattr(settings, item.name, value)

        return settings


@dataclass
class UserProfile:
    """Everything saved for the user."""

    settings: UserSettings = field(default_factory=UserSettings)
    bankroll: Bankroll = field(default_factory=Bankroll)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": PROFILE_FORMAT_VERSION,
            "settings": self.settings.to_dict(),
            "bankroll": self.bankroll.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: object) -> "UserProfile":
        if not isinstance(data, dict):
            raise ProfileError("The profile is not an object.")

        version = data.get("format_version")

        if version != PROFILE_FORMAT_VERSION:
            raise ProfileError(
                f"Unsupported profile format version {version!r}; "
                f"this version of the application reads version "
                f"{PROFILE_FORMAT_VERSION}."
            )

        try:
            bankroll = (
                Bankroll.from_dict(data["bankroll"])
                if "bankroll" in data
                else Bankroll()
            )
        except BankrollDataError as error:
            raise ProfileError(str(error)) from error

        return cls(
            settings=UserSettings.from_dict(data.get("settings", {})),
            bankroll=bankroll,
        )


def read_profile(path: Path) -> UserProfile:
    """Read a profile file; raises ``ProfileError`` if it cannot be used."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProfileError(f"{path.name} cannot be read: {error}") from error

    return UserProfile.from_dict(data)


class ProfileStore:
    """The user profile and the file it is saved in.

    Without a path the profile only lives in memory: nothing is read or
    written (used by tests and when no data folder is available).
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.warning: str | None = None
        """A message for the user when the saved profile could not be used."""
        self.profile = self._load() if path is not None else UserProfile()

    @property
    def backup_path(self) -> Path | None:
        return None if self.path is None else self.path.with_suffix(".bak")

    @property
    def settings(self) -> UserSettings:
        return self.profile.settings

    @property
    def bankroll(self) -> Bankroll:
        return self.profile.bankroll

    def save(self) -> None:
        """Write the profile atomically, keeping the previous file as backup."""
        if self.path is None:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(self.profile.to_dict(), indent=4, ensure_ascii=False),
            encoding="utf-8",
        )

        if self.path.exists():
            assert self.backup_path is not None
            shutil.copyfile(self.path, self.backup_path)

        temporary_path.replace(self.path)

    def _load(self) -> UserProfile:
        path = self.path
        backup = self.backup_path
        assert path is not None and backup is not None

        if not path.exists():
            if backup.exists():  # Interrupted between two steps of a save.
                return self._load_backup(path, reason=f"{path.name} is missing")

            return UserProfile()  # First launch.

        try:
            return read_profile(path)
        except ProfileError as error:
            kept = self._keep_damaged_file(path)
            reason = f"{error} (the damaged file was kept as {kept.name})"

            if backup.exists():
                return self._load_backup(path, reason=reason)

            self.warning = f"Your profile could not be loaded: {reason}."
            return UserProfile()

    def _load_backup(self, path: Path, reason: str) -> UserProfile:
        backup = self.backup_path
        assert backup is not None

        try:
            profile = read_profile(backup)
        except ProfileError as error:
            self.warning = (
                f"Your profile could not be loaded: {reason}; "
                f"the backup is damaged too: {error}."
            )
            return UserProfile()

        self.warning = f"Your profile was restored from its backup: {reason}."
        return profile

    @staticmethod
    def _keep_damaged_file(path: Path) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        kept = path.with_name(f"{path.stem}.damaged_{timestamp}{path.suffix}")
        path.replace(kept)

        return kept
