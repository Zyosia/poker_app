"""The session browser (V1.1): saved games, their result, chip graph and hands.

Every game played in the application is saved in the sessions folder. The
browser lists them, most recent first; a session shows your result, your
chips hand after hand, and every hand, which the replayer opens.

PokerStars and Winamax hand histories opened here are kept in the library
(V2.1), and a session can be deleted, after a confirmation.
"""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.application.game_modes import MODE_LABELS, GameMode
from backend.application.hand_records import (
    HandRecord,
    SessionLibrary,
    SessionRecord,
)
from backend.application.persistence import SessionFileError
from backend.poker_engine.blinds import BlindLevel
from frontend.components.line_chart import LineChart
from frontend.formatting import format_cards, format_chips

from .arena_results_screen import SortableItem

SESSION_COLUMNS = ("Date", "Mode", "Hands", "Result", "Replays")
HAND_COLUMNS = ("Hand", "Blinds", "Position", "Cards", "Board", "Result", "Pot")
ORDINALS = {1: "1st", 2: "2nd", 3: "3rd"}


def confirm_delete(parent: QWidget, session: SessionRecord) -> bool:
    """Ask before deleting a session: it cannot be undone."""
    what = (
        f"the {session.source} hand history {session.path.name}"
        if session.imported
        else f"the session of {session.started:%d %b %Y %H:%M}"
    )
    answer = QMessageBox.question(
        parent,
        "Delete the session",
        f"Delete {what} ({len(session.hands)} hands)?\n\n"
        "Its hands will no longer be listed, replayed or counted in your "
        "stats. This cannot be undone.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )

    return answer == QMessageBox.StandardButton.Yes


def signed(chips: int) -> str:
    return ("+" if chips > 0 else "") + format_chips(chips)


def short_blinds(level: BlindLevel) -> str:
    """For example "30/60, ante 60"."""
    text = f"{level.small_blind}/{level.big_blind}"

    return f"{text}, ante {level.ante}" if level.ante else text


def stored_index(table: QTableWidget, row: int) -> int:
    """The list index kept in the first cell of a row (rows can be sorted)."""
    item = table.item(row, 0)
    assert item is not None

    return item.data(Qt.ItemDataRole.UserRole)


def selected_index(table: QTableWidget) -> int | None:
    rows = table.selectionModel().selectedRows()

    return stored_index(table, rows[0].row()) if rows else None


def select_index(table: QTableWidget, index: int) -> None:
    """Select the row holding list item ``index``, wherever sorting put it."""
    for row in range(table.rowCount()):
        if stored_index(table, row) == index:
            table.selectRow(row)
            return


def session_result(session: SessionRecord) -> tuple[str, float]:
    """The result shown for a session, and the value it is sorted by."""
    if session.mode == GameMode.CASH or session.imported:
        return signed(session.net_chips), session.net_chips

    finish = session.finish

    if finish is None:
        return "Not finished", float("-inf")

    place = ORDINALS.get(finish.place, f"{finish.place}th")
    text = f"{place} of {finish.entrants}  ({signed(finish.profit)})"

    return text, finish.profit


class SessionBrowserScreen(QWidget):
    """Lists the saved sessions and the hands of the one selected."""

    replay_requested = Signal(object, int)
    """Emitted with a ``SessionRecord`` and the index of the hand to replay."""
    back_requested = Signal()

    def __init__(
        self, library: SessionLibrary | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.library = library or SessionLibrary()
        self.in_use: Callable[[], set[Path]] = set
        """The session files of the games being played: never deleted."""
        self.sessions: list[SessionRecord] = []
        self.visible_sessions: list[SessionRecord] = []
        self.session: SessionRecord | None = None

        title = QLabel("SESSIONS")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All", None)

        for mode, label in MODE_LABELS.items():
            self.filter_combo.addItem(label, mode)

        self.filter_combo.currentIndexChanged.connect(self._fill_sessions)
        self.notice_label = QLabel()
        self.notice_label.setObjectName("errorText")
        self.open_button = QPushButton("Open file…")
        self.open_button.setObjectName("small")
        self.open_button.clicked.connect(self._on_open_clicked)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("small")
        self.refresh_button.clicked.connect(self.refresh)

        self.sessions_table = self._table(SESSION_COLUMNS)
        self.sessions_table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        self.sessions_table.itemSelectionChanged.connect(self._on_session_selected)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("statusText")
        self.summary_label.setWordWrap(True)
        self.chart = LineChart()
        self.chart.setMinimumSize(360, 200)
        self.chart.y_label = "Your net chips"
        self.hands_table = self._table(HAND_COLUMNS)
        header = self.hands_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(
            HAND_COLUMNS.index("Board"), QHeaderView.ResizeMode.Stretch
        )
        self.hands_table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.hands_table.itemSelectionChanged.connect(self._update_replay_button)
        self.hands_table.itemDoubleClicked.connect(lambda _item: self.replay_selected())

        self.delete_button = QPushButton("Delete session")
        self.delete_button.setObjectName("danger")
        self.delete_button.clicked.connect(self.delete_selected)
        self.replay_button = QPushButton("Replay hand")
        self.replay_button.setObjectName("primary")
        self.replay_button.clicked.connect(self.replay_selected)
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.back_requested)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Show"))
        filters.addWidget(self.filter_combo)
        filters.addWidget(self.notice_label, stretch=1)
        filters.addWidget(self.open_button)
        filters.addWidget(self.refresh_button)

        left = QVBoxLayout()
        left.addLayout(filters)
        left.addWidget(self.sessions_table)

        right = QVBoxLayout()
        right.addWidget(self.summary_label)
        right.addWidget(self.chart, stretch=2)
        right.addWidget(self.hands_table, stretch=3)

        body = QHBoxLayout()
        body.addLayout(left, stretch=5)
        body.addLayout(right, stretch=6)

        buttons = QHBoxLayout()
        buttons.addWidget(self.delete_button)
        buttons.addStretch()
        buttons.addWidget(self.replay_button)
        buttons.addWidget(self.back_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.addWidget(title)
        layout.addLayout(body, stretch=1)
        layout.addLayout(buttons)

    @staticmethod
    def _table(columns: tuple[str, ...]) -> QTableWidget:
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setStretchLastSection(True)

        return table

    # --- Sessions ------------------------------------------------------------

    def refresh(self) -> None:
        """Read the sessions folder and the imported histories again
        (unchanged files are not re-read)."""
        scan = self.library.scan(include_imports=True)
        outside = [s for s in self.sessions if not self.library.owns(s.path)]
        self.sessions = outside + list(scan.sessions)
        count = len(scan.unreadable)
        self.notice_label.setText(
            f"{count} file{'s' if count > 1 else ''} could not be read."
            if count
            else ""
        )
        self.notice_label.setToolTip("\n".join(scan.unreadable))
        self._fill_sessions()

    def open_file(self, path: Path) -> None:
        """Show a session file, or a PokerStars or Winamax hand history, from
        anywhere; it joins the list. A hand history is kept in the library,
        so it is listed again next time."""
        try:
            if path.suffix.lower() == ".dat":
                session = self.library.load(path)
            else:
                session = self.library.import_history(path)
        except (SessionFileError, OSError) as error:
            self.notice_label.setText(str(error))
            return

        self.sessions = [s for s in self.sessions if s.path != session.path]
        self.sessions.insert(0, session)
        self.filter_combo.setCurrentIndex(0)
        self._fill_sessions()

    def _on_open_clicked(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self,
            "Open a session file or a hand history",
            str(self.library.directory),
            "Sessions and hand histories (*.dat *.txt);;All files (*)",
        )

        if name:
            self.open_file(Path(name))

    def _fill_sessions(self) -> None:
        wanted = self.filter_combo.currentData()
        self.visible_sessions = [
            session for session in self.sessions if wanted in (None, session.mode)
        ]
        table = self.sessions_table
        table.setSortingEnabled(False)
        table.setRowCount(len(self.visible_sessions))

        for row, session in enumerate(self.visible_sessions):
            result, result_value = session_result(session)
            started = session.started.timestamp()
            cells = (
                SortableItem(f"{session.started:%Y-%m-%d %H:%M}", started),
                QTableWidgetItem(MODE_LABELS[session.mode]),
                SortableItem(str(len(session.hands)), len(session.hands)),
                SortableItem(result, result_value),
                SortableItem(str(session.replayable_hands), session.replayable_hands),
            )
            cells[0].setData(Qt.ItemDataRole.UserRole, row)

            for column, item in enumerate(cells):
                table.setItem(row, column, item)

        table.setSortingEnabled(True)
        table.clearSelection()  # So that selecting row 0 is always a change.

        if self.visible_sessions:
            table.selectRow(0)
        else:
            self.show_session(None)

    def _on_session_selected(self) -> None:
        index = selected_index(self.sessions_table)

        if index is not None:
            self.show_session(self.visible_sessions[index])

    # --- One session ---------------------------------------------------------

    def show_session(self, session: SessionRecord | None) -> None:
        self.session = session
        table = self.hands_table
        table.setSortingEnabled(False)

        if session is None:
            self.summary_label.setText(
                "No saved session yet: every game you play is saved here."
            )
            self.chart.set_series([], [])
            table.setRowCount(0)
            self._update_replay_button()
            return

        self.summary_label.setText(self._summary(session))
        self.summary_label.setToolTip("\n".join(session.notes))
        self.chart.set_series(
            [session.human],
            [(hands, (net,)) for hands, net in session.chart_points()],
        )
        table.setRowCount(len(session.hands))

        for row, hand in enumerate(session.hands):
            cells = self._hand_cells(session, hand)
            cells[0].setData(Qt.ItemDataRole.UserRole, row)

            for column, item in enumerate(cells):
                table.setItem(row, column, item)

        table.setSortingEnabled(True)
        table.clearSelection()

        if session.hands:
            table.selectRow(0)

        self._update_replay_button()

    @staticmethod
    def _summary(session: SessionRecord) -> str:
        players = ", ".join(
            name for name in session.seat_names if name != session.human
        )
        result, _ = session_result(session)
        first = [
            f"{MODE_LABELS[session.mode]} — {session.started:%d %b %Y %H:%M}",
            f"{session.human} against {players}",
        ]

        if session.imported:
            first.insert(0, f"Imported from {session.source}")
        second = [f"{len(session.hands)} hands", f"result {result}"]

        if session.finish is not None and session.finish.multiplier:
            second.append(f"prize multiplier × {session.finish.multiplier}")

        if session.replayable_hands < len(session.hands):
            second.append("hands saved before V1.1 cannot be replayed")

        if session.notes:
            second.append(f"{len(session.notes)} hands not played by this engine")

        return "   ·   ".join(first) + "\n" + "   ·   ".join(second)

    @staticmethod
    def _hand_cells(session: SessionRecord, hand: HandRecord) -> list[QTableWidgetItem]:
        human = session.human
        dealt_in = human in hand.players
        cards = hand.hole_cards(human)
        net = hand.net_result(human)

        return [
            SortableItem(f"#{hand.number}", hand.number),
            QTableWidgetItem(short_blinds(hand.blind_level)),
            QTableWidgetItem((hand.position_of(human) or "—") if dealt_in else "out"),
            QTableWidgetItem(format_cards(cards) if cards else "—"),
            QTableWidgetItem(format_cards(hand.board) or "—"),
            SortableItem(signed(net) if dealt_in else "—", net),
            SortableItem(format_chips(hand.pot), hand.pot),
        ]

    def selected_hand_index(self) -> int | None:
        return selected_index(self.hands_table)

    def select_hand(self, index: int) -> None:
        select_index(self.hands_table, index)

    def replay_selected(self) -> None:
        index = self.selected_hand_index()

        if self.session is not None and index is not None:
            self.replay_requested.emit(self.session, index)

    def _update_replay_button(self) -> None:
        index = self.selected_hand_index()
        self.replay_button.setEnabled(self.session is not None and index is not None)
        self._update_delete_button()

    def _update_delete_button(self) -> None:
        session = self.session
        reason = self._cannot_delete(session)
        self.delete_button.setEnabled(session is not None and reason is None)
        self.delete_button.setToolTip(
            reason or "Delete this session for good: its hands leave your stats."
        )

    def _cannot_delete(self, session: SessionRecord | None) -> str | None:
        if session is None:
            return "No session selected."

        if not self.library.owns(session.path):
            return "This file is outside the session folder: it is only shown here."

        if session.path.resolve() in {p.resolve() for p in self.in_use()}:
            return "This game is still being played."

        return None

    def delete_selected(self) -> None:
        """Delete the selected session, once the user confirms."""
        session = self.session

        if session is None or self._cannot_delete(session) is not None:
            return

        if not confirm_delete(self, session):
            return

        self.library.delete(session)
        self.sessions = [s for s in self.sessions if s.path != session.path]
        self._fill_sessions()
