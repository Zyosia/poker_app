"""Saved sessions read back as typed records.

The session browser, the hand replayer and "My stats" work from these
records. Every format version is read (see ``persistence``). Hands saved
before format 4 have no ``seats``: their hole cards and starting stacks were
not recorded, so they cannot be replayed, but their actions, board, pots and
payouts are known, which is enough for results and stats.

The library also keeps the **imported hand histories** (PokerStars,
Winamax): a file opened in the session browser is copied to its ``imports``
folder, so it is listed again at the next launch. Imported hands are never
counted in "My stats" (they were not played in this application), and
deleting a session removes its file for good.
"""

import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.poker_engine.blinds import AnteType, BlindLevel
from backend.poker_engine.constants import Card, Position, Street
from backend.poker_engine.hand_evaluator import HandCategory, HandEvaluation
from backend.poker_engine.models import ActionEvent, PotResult, SeatRecord, StreetEvent
from backend.poker_engine.session import GameSession

from .game_modes import GameMode
from .persistence import (
    SESSION_DIR,
    SessionFileError,
    load_session_file,
    serialize_session,
)

FORCED_ACTIONS = ("post_sb", "post_bb", "post_ante", "post_straddle")
"""Recorded by the engine itself when a hand starts: not decisions."""
SESSION_FILE_GLOB = "*.dat"
IMPORTS_FOLDER = "imports"
HISTORY_FILE_GLOB = "*.txt"
FILE_DATE_FORMAT = "pk_sess_%Y%m%d_%H%M%S"
APP_SOURCE = "Poker app"


@dataclass(frozen=True)
class HandRecord:
    """One finished (or interrupted) hand, as saved."""

    number: int
    blind_level: BlindLevel
    dealer: str
    seats: tuple[SeatRecord, ...] | None
    """The players dealt in as the hand started; None before format 4."""
    actions: tuple[ActionEvent, ...]
    streets: tuple[StreetEvent, ...]
    pot_results: tuple[PotResult, ...]
    showdown: Mapping[str, HandEvaluation]
    payouts: Mapping[str, int]
    winner_by_fold: str | None
    revealed_after_action: int | None
    timed_out_actions: tuple[int, ...]
    finished: bool
    hidden: frozenset[str] = frozenset()
    """Players whose cards nobody saw (hands from another site's history):
    their seats hold stand-in cards, which are never shown."""
    hand_id: str | None = None
    """The site's number of the hand, for a hand from another site."""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HandRecord":
        seats = data.get("seats")

        actions = tuple(_action(event) for event in data["actions"])
        # Files saved before format 4 hold the table's dealer at the time of
        # the save, not the hand's: the Button position is the hand's own.
        dealer = next(
            (e.player for e in actions if e.position == Position.BTN), data["dealer"]
        )

        return cls(
            number=data["hand_number"],
            blind_level=_blind_level(data["blind_level"]),
            dealer=dealer,
            seats=None if seats is None else tuple(_seat(seat) for seat in seats),
            actions=actions,
            streets=tuple(
                StreetEvent(Street(event["street"]), tuple(event["community_cards"]))
                for event in data["streets"]
            ),
            pot_results=tuple(_pot_result(result) for result in data["pot_results"]),
            showdown={
                name: HandEvaluation(
                    rank=HandCategory(shown["rank"]),
                    name=shown["name"],
                    cards=tuple(shown["cards"]),
                    tiebreaker=tuple(shown["tiebreaker"]),
                )
                for name, shown in data["showdown"].items()
            },
            payouts=dict(data["payouts"]),
            winner_by_fold=data["winner_by_fold"],
            revealed_after_action=data["revealed_after_action"],
            timed_out_actions=tuple(data["timed_out_actions"]),
            finished=data["finished"],
        )

    @property
    def replayable(self) -> bool:
        """True when the hole cards and stacks were recorded (format 4)."""
        return self.seats is not None and self.finished

    @property
    def big_blind(self) -> int:
        return self.blind_level.big_blind

    @property
    def board(self) -> tuple[Card, ...]:
        return self.streets[-1].community_cards if self.streets else ()

    @property
    def pot(self) -> int:
        """Every chip put in the pot, antes included."""
        return sum(event.amount for event in self.actions)

    @property
    def players(self) -> tuple[str, ...]:
        """The players dealt in: seat order when known, else order of action.

        A player dealt in always has an action: an ante, a blind or a decision.
        """
        if self.seats is not None:
            return tuple(seat.name for seat in self.seats)

        return tuple(dict.fromkeys(event.player for event in self.actions))

    def seat(self, name: str) -> SeatRecord | None:
        if self.seats is None:
            return None

        return next((seat for seat in self.seats if seat.name == name), None)

    def hole_cards(self, name: str) -> tuple[Card, ...] | None:
        seat = self.seat(name)

        return None if seat is None else seat.hole_cards

    def position_of(self, name: str) -> Position | None:
        seat = self.seat(name)

        if seat is not None:
            return seat.position

        return next((e.position for e in self.actions if e.player == name), None)

    def contributed(self, name: str) -> int:
        """Chips ``name`` put in the pot, antes and blinds included."""
        return sum(event.amount for event in self.actions if event.player == name)

    def net_result(self, name: str) -> int:
        """Chips won or lost by ``name`` in this hand."""
        return self.payouts.get(name, 0) - self.contributed(name)


@dataclass(frozen=True)
class TournamentFinish:
    """The human's result in a finished tournament or Spin & Go."""

    place: int
    entrants: int
    prize: int
    invested: int
    """Buy-in, rebuys and add-on."""
    buy_in: int
    multiplier: int | None

    @property
    def profit(self) -> int:
        return self.prize - self.invested


@dataclass(frozen=True)
class SessionRecord:
    """A saved session and its hands, seen from the human player."""

    path: Path
    started: datetime
    mode: GameMode
    human: str
    seat_names: tuple[str, ...]
    hands: tuple[HandRecord, ...]
    finish: TournamentFinish | None
    """The human's result once a tournament is over; None otherwise."""
    source: str = APP_SOURCE
    """Where the hands come from: this application, PokerStars or Winamax."""
    notes: tuple[str, ...] = ()
    """Hands of the file that could not be read, one message each."""

    @property
    def imported(self) -> bool:
        return self.source != APP_SOURCE

    @property
    def replayable_hands(self) -> int:
        return sum(hand.replayable for hand in self.hands)

    def hand_results(self) -> list[int]:
        """The human's net result of every hand."""
        return [hand.net_result(self.human) for hand in self.hands]

    @property
    def net_chips(self) -> int:
        """Chips won or lost by the human over the hands of the session."""
        return sum(self.hand_results())

    def chart_points(self) -> list[tuple[int, int]]:
        """(hands played, cumulative net chips), starting from (0, 0)."""
        points = [(0, 0)]
        total = 0

        for hand, result in zip(self.hands, self.hand_results(), strict=True):
            total += result
            points.append((hand.number, total))

        return points


def live_session_record(
    session: GameSession, human: str, mode: GameMode
) -> SessionRecord:
    """The record of a game still being played (its hands so far), read
    from memory: the replayer of a table works even when nothing is saved."""
    data = serialize_session(session, human=human, mode=mode)

    try:
        return _session_record(Path(), data, started=datetime.now())
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise SessionFileError(f"The game cannot be replayed: {error!r}") from error


def load_session_record(path: Path) -> SessionRecord:
    """Read a saved session; raises ``SessionFileError`` if it cannot be."""
    data = load_session_file(path)

    try:
        return _session_record(path, data)
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise SessionFileError(
            f"{path.name} is not a valid session file: {error!r}"
        ) from error


@dataclass(frozen=True)
class LibraryScan:
    sessions: tuple[SessionRecord, ...]
    """Most recent first."""
    unreadable: tuple[str, ...]
    """One message per file that could not be read."""


class SessionLibrary:
    """The saved sessions of a folder; unchanged files are read only once."""

    def __init__(self, directory: Path = SESSION_DIR) -> None:
        self.directory = directory
        self._cache: dict[Path, tuple[tuple[int, int], SessionRecord]] = {}

    @property
    def imports_directory(self) -> Path:
        return self.directory / IMPORTS_FOLDER

    def scan(self, include_imports: bool = False) -> LibraryScan:
        """The sessions played in the application, most recent first; with
        ``include_imports``, the imported hand histories too."""
        paths = _files(self.directory, SESSION_FILE_GLOB)

        if include_imports:
            paths += _files(self.imports_directory, HISTORY_FILE_GLOB)

        sessions: list[SessionRecord] = []
        unreadable: list[str] = []

        for path in paths:
            try:
                sessions.append(self.load(path))
            except (SessionFileError, OSError) as error:
                unreadable.append(str(error))

        if include_imports:  # A full scan: forget the files that are gone.
            present = set(paths)
            self._cache = {
                path: entry for path, entry in self._cache.items() if path in present
            }

        sessions.sort(key=lambda session: (session.started, session.path), reverse=True)

        return LibraryScan(tuple(sessions), tuple(unreadable))

    def load(self, path: Path) -> SessionRecord:
        """A session file, or a PokerStars or Winamax hand history (.txt)."""
        status = path.stat()
        version = (status.st_mtime_ns, status.st_size)
        cached = self._cache.get(path)

        if cached is not None and cached[0] == version:
            return cached[1]

        if path.suffix.lower() == ".dat":
            record = load_session_record(path)
        else:
            # Imported here: hand_import builds on this module's records.
            from .hand_import import read_hand_history_file

            record = read_hand_history_file(path)

        self._cache[path] = (version, record)

        return record

    def import_history(self, path: Path) -> SessionRecord:
        """Keep a copy of a hand history in the library, and read it.

        A file already imported (same name and content) is not copied again;
        another file of the same name gets a numbered name.
        """
        if self.owns(path):
            return self.load(path)

        from .hand_import import read_hand_history_file

        read_hand_history_file(path)  # Only a readable history is kept.
        self.imports_directory.mkdir(parents=True, exist_ok=True)
        target = self._import_target(path)

        if not target.exists():
            shutil.copyfile(path, target)

        return self.load(target)

    def _import_target(self, path: Path) -> Path:
        content = path.read_bytes()
        target = self.imports_directory / path.name
        number = 1

        while target.exists() and target.read_bytes() != content:
            number += 1
            target = self.imports_directory / f"{path.stem} ({number}){path.suffix}"

        return target

    def owns(self, path: Path) -> bool:
        """True for a file of the library (a session or an import)."""
        folder = path.resolve().parent

        return folder in (self.directory.resolve(), self.imports_directory.resolve())

    def delete(self, session: SessionRecord) -> None:
        """Delete a session (or an imported history) from the library, for good.

        Raises ``ValueError`` for a file outside the library: it is not the
        library's to delete.
        """
        if not self.owns(session.path):
            raise ValueError(f"{session.path.name} is not in the session library.")

        session.path.unlink(missing_ok=True)
        self._cache.pop(session.path, None)

    def delete_all(self) -> int:
        """Delete every session and imported history; returns how many."""
        paths = _files(self.directory, SESSION_FILE_GLOB) + _files(
            self.imports_directory, HISTORY_FILE_GLOB
        )

        for path in paths:
            path.unlink(missing_ok=True)

        self._cache.clear()

        return len(paths)


def _files(directory: Path, pattern: str) -> list[Path]:
    return sorted(directory.glob(pattern)) if directory.is_dir() else []


# --- Parsing -------------------------------------------------------------------


def _session_record(
    path: Path, data: Mapping[str, Any], started: datetime | None = None
) -> SessionRecord:
    seat_names = tuple(player["name"] for player in data["session"]["players"])
    hands = tuple(HandRecord.from_dict(hand) for hand in data["hands"])
    human = data.get("human") or seat_names[0]  # The app seats the human first.
    tournament = data.get("tournament")

    return SessionRecord(
        path=path,
        started=started or _started(path),
        mode=_mode(data, hands),
        human=human,
        seat_names=seat_names,
        hands=hands,
        finish=_finish(tournament, human) if tournament else None,
    )


def _started(path: Path) -> datetime:
    """The time in the file name, else the time of the last save."""
    try:
        return datetime.strptime(path.stem, FILE_DATE_FORMAT)
    except ValueError:
        return datetime.fromtimestamp(path.stat().st_mtime)


def _mode(data: Mapping[str, Any], hands: tuple[HandRecord, ...]) -> GameMode:
    """The recorded mode; guessed for files saved before format 4."""
    if data.get("mode"):
        return GameMode(data["mode"])

    tournament = data.get("tournament")

    if tournament:
        return GameMode.SPIN if tournament.get("multiplier") else GameMode.TOURNAMENT

    levels = {hand.blind_level for hand in hands}

    if len(levels) > 1 or any(level.ante for level in levels):
        return GameMode.TOURNAMENT

    return GameMode.CASH


def _finish(tournament: Mapping[str, Any], human: str) -> TournamentFinish | None:
    finishes = tournament["finishes"]
    own = next((finish for finish in finishes if finish["name"] == human), None)

    if own is None:
        return None

    return TournamentFinish(
        place=own["place"],
        entrants=len(finishes),
        prize=own["prize"],
        invested=own["invested"],
        buy_in=tournament["buy_in"],
        multiplier=tournament.get("multiplier"),
    )


def _blind_level(data: Mapping[str, Any]) -> BlindLevel:
    return BlindLevel(
        small_blind=data["small_blind"],
        big_blind=data["big_blind"],
        ante=data["ante"],
        ante_type=AnteType(data["ante_type"]),
    )


def _seat(data: Mapping[str, Any]) -> SeatRecord:
    return SeatRecord(
        name=data["name"],
        stack=data["stack"],
        position=Position(data["position"]),
        hole_cards=tuple(data["hole_cards"]),
    )


def _action(data: Mapping[str, Any]) -> ActionEvent:
    position = data["position"]

    return ActionEvent(
        sequence=data["sequence"],
        street=Street(data["street"]),
        player=data["player"],
        position=None if position is None else Position(position),
        action=data["action"],
        amount=data["amount"],
        bet_before=data["bet_before"],
        bet_after=data["bet_after"],
        pot_after=data["pot_after"],
        current_bet_after=data["current_bet_after"],
        bet_initiator=data["bet_initiator"],
    )


def _pot_result(data: Mapping[str, Any]) -> PotResult:
    return PotResult(
        amount=data["amount"],
        eligible_players=tuple(data["eligible_players"]),
        winners=tuple(data["winners"]),
        decisive_tiebreaker=data["decisive_tiebreaker"],
        decisive_value=data["decisive_value"],
    )
