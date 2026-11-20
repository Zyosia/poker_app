"""The lobby of a tournament, in a window of its own beside the table (V3.1).

Like an online room's tournament lobby: the prize pool, the blind level and
the next one, the players left, the average stack; the payouts and the
levels; every player sorted by stack (with a search), then the players out
by place; and the tables, each with its players. It opens when a
multi-table tournament starts, from the table's Lobby button too, and
follows the tournament between hands while the table goes on.
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from backend.application.tournament import Tournament
from backend.poker_engine.models import Player
from frontend.formatting import format_chips

from .tournament_screen import format_seconds, level_parts, ordinal, table_part

WINDOW_SIZE = (1080, 700)
CLOCK_MS = 1000
YOU_COLOR = "#f2c14e"
OUT_COLOR = "#7d8794"


def read_only_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    return table


def fill_row(
    table: QTableWidget, row: int, cells: tuple[str, ...], color: str | None = None
) -> None:
    font = QFont()
    font.setBold(color == YOU_COLOR)

    for column, text in enumerate(cells):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        if color is not None:
            item.setForeground(QColor(color))
            item.setFont(font)

        table.setItem(row, column, item)


def stack_text(stack: int, big_blind: int) -> str:
    return f"{format_chips(stack)} ({stack / big_blind:.1f} BB)"


class InfoCard(QFrame):
    """A caption and a value, like 'Players · 33 / 44'."""

    def __init__(self, caption: str) -> None:
        super().__init__()
        self.setObjectName("guideCard")
        caption_label = QLabel(caption)
        caption_label.setObjectName("hintText")
        self.value_label = QLabel("—")
        self.value_label.setObjectName("summaryText")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        layout.addWidget(caption_label)
        layout.addWidget(self.value_label)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


class TournamentLobbyWindow(QWidget):
    """Everything about a running tournament, beside its table."""

    watch_requested = Signal(int)
    """The number of another table to watch in a window of its own."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("guideWindow")  # The application's dark background.
        self.setWindowTitle(f"Lobby · {title}")
        self.resize(*WINDOW_SIZE)
        self.tournament: Tournament | None = None
        self.human_name = ""

        self.title_label = QLabel("TOURNAMENT")
        self.title_label.setObjectName("guideTitle")
        self.level_label = QLabel()
        self.level_label.setObjectName("statusText")

        self.prize_card = InfoCard("Prize pool")
        self.players_card = InfoCard("Players")
        self.average_card = InfoCard("Average stack")
        self.place_card = InfoCard("Your place")
        self.tables_card = InfoCard("Tables")
        self.played_card = InfoCard("Played")
        cards = QGridLayout()
        cards.setSpacing(10)

        for index, card in enumerate(
            (
                self.prize_card,
                self.players_card,
                self.average_card,
                self.place_card,
                self.tables_card,
                self.played_card,
            )
        ):
            cards.addWidget(card, 0, index)

        self.payouts_table = read_only_table(["Place", "Prize"])
        self.levels_table = read_only_table(["Level", "Blinds", "Ante"])
        left_tabs = QTabWidget()
        left_tabs.addTab(self.payouts_table, "Payouts")
        left_tabs.addTab(self.levels_table, "Levels")

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search a player")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._filter_players)
        self.players_table = read_only_table(["Place", "Name", "Stack", "Table"])
        players_page = QWidget()
        players_layout = QVBoxLayout(players_page)
        players_layout.setContentsMargins(0, 8, 0, 0)
        players_layout.addWidget(self.search_edit)
        players_layout.addWidget(self.players_table, stretch=1)

        self.tables_table = read_only_table(["Table", "Players", "Biggest", "Smallest"])
        self.tables_table.itemSelectionChanged.connect(self._show_selected_table)
        self.tables_table.cellDoubleClicked.connect(lambda: self._watch_selected())
        self.seats_table = read_only_table(["Seat", "Name", "Stack"])
        self.watch_button = QPushButton("Watch table")
        self.watch_button.setToolTip(
            "Watch the selected table play in a window of its own (or "
            "double-click a table)."
        )
        self.watch_button.clicked.connect(self._watch_selected)
        seats_page = QWidget()
        seats_layout = QVBoxLayout(seats_page)
        seats_layout.setContentsMargins(0, 0, 0, 0)
        seats_layout.addWidget(self.seats_table, stretch=1)
        seats_layout.addWidget(self.watch_button, alignment=Qt.AlignmentFlag.AlignRight)
        tables_page = QSplitter(Qt.Orientation.Vertical)
        tables_page.addWidget(self.tables_table)
        tables_page.addWidget(seats_page)

        right_tabs = QTabWidget()
        right_tabs.addTab(players_page, "Players")
        right_tabs.addTab(tables_page, "Tables")
        self.right_tabs = right_tabs

        body = QHBoxLayout()
        body.setSpacing(14)
        body.addWidget(left_tabs, stretch=2)
        body.addWidget(right_tabs, stretch=3)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(self.title_label)
        layout.addWidget(self.level_label)
        layout.addLayout(cards)
        layout.addLayout(body, stretch=1)

        self._clock_timer = QTimer(self)
        """The level line, every second (levels by time)."""
        self._clock_timer.setInterval(CLOCK_MS)
        self._clock_timer.timeout.connect(self.refresh_header)

    # --- Showing -------------------------------------------------------------

    def show_tournament(self, tournament: Tournament, human_name: str) -> None:
        """Follow ``tournament``; bring the window to the front."""
        self.tournament = tournament
        self.human_name = human_name
        self.refresh()
        self.show()
        self.raise_()

    def refresh(self) -> None:
        """Everything, from the tournament's state now (between two hands)."""
        if self.tournament is None:
            return

        self.refresh_header()
        self._fill_payouts()
        self._fill_levels()
        self._fill_players()
        self._fill_tables()

        if self.tournament.clock is not None and not self.tournament.is_finished:
            self._clock_timer.start()
        else:
            self._clock_timer.stop()

    def refresh_header(self) -> None:
        tournament = self.tournament

        if tournament is None:
            return

        level = tournament.level
        parts = level_parts(tournament)
        table = table_part(tournament)

        if table is not None:
            parts.insert(0, table)

        if tournament.is_finished:
            parts = [f"FINISHED — won by {tournament.result.winner.name}"]

        self.level_label.setText("   ·   ".join(parts))
        left = tournament.players_left()
        self.prize_card.set_value(format_chips(tournament.prize_pool))
        self.players_card.set_value(f"{len(left)} / {tournament.entrants}")
        self.average_card.set_value(
            stack_text(round(tournament.average_stack()), level.big_blind)
        )
        you = tournament.player(self.human_name)
        place = tournament.current_place(self.human_name)
        self.place_card.set_value(
            f"Out in {ordinal(place)}" if you.is_eliminated else ordinal(place)
        )
        self.tables_card.set_value(str(len(tournament.tables)))

        if tournament.clock is not None:
            played = format_seconds(tournament.clock.elapsed())
        else:
            played = f"{tournament.hands_played} hands"

        self.played_card.set_value(played)

    def _fill_payouts(self) -> None:
        tournament = self.tournament
        assert tournament is not None
        prizes = [
            prize
            for prize in tournament.payout.prizes(
                tournament.prize_pool, tournament.entrants
            )
            if prize > 0
        ]
        table = self.payouts_table
        table.setRowCount(len(prizes))

        for row, prize in enumerate(prizes):
            fill_row(table, row, (ordinal(row + 1), format_chips(prize)))

    def _fill_levels(self) -> None:
        tournament = self.tournament
        assert tournament is not None
        levels = tournament.config.structure.levels
        table = self.levels_table
        table.setRowCount(len(levels))

        for row, level in enumerate(levels):
            color = YOU_COLOR if row == tournament.level_index else None
            ante = format_chips(level.ante) if level.ante else "—"
            blinds = (
                f"{format_chips(level.small_blind)} / {format_chips(level.big_blind)}"
            )
            fill_row(table, row, (str(row + 1), blinds, ante), color)

    def _fill_players(self) -> None:
        """The players left by stack, then the players out by place."""
        tournament = self.tournament
        assert tournament is not None
        big_blind = tournament.level.big_blind
        left = sorted(tournament.players_left(), key=lambda p: -p.stack)
        out = sorted(
            (p for p in tournament.players if p.is_eliminated),
            key=lambda p: tournament.current_place(p.name),
        )
        prizes = tournament.payout.prizes(tournament.prize_pool, tournament.entrants)
        seated = {
            player.name: seat_table.number
            for seat_table in tournament.tables
            for player in (*seat_table.session.players, *seat_table.incoming)
        }
        table = self.players_table
        table.setRowCount(len(left) + len(out))

        for row, player in enumerate(left):
            cells = (
                ordinal(row + 1),
                player.name,
                stack_text(player.stack, big_blind),
                str(seated.get(player.name, "—")),
            )
            fill_row(table, row, cells, self._color(player))

        for row, player in enumerate(out, start=len(left)):
            place = tournament.current_place(player.name)
            prize = prizes[place - 1]
            cells = (
                ordinal(place),
                player.name,
                "Out",
                f"Won {format_chips(prize)}" if prize else "—",
            )
            fill_row(table, row, cells, self._color(player) or OUT_COLOR)

        self._filter_players()

    def _fill_tables(self) -> None:
        tournament = self.tournament
        assert tournament is not None
        selected = self._selected_table_row()
        table = self.tables_table
        table.blockSignals(True)
        table.setRowCount(len(tournament.tables))

        for row, seat_table in enumerate(tournament.tables):
            stacks = [p.stack for p in seat_table.session.players if p.stack > 0]
            yours = seat_table.number == 1 and not (
                tournament.player(self.human_name).is_eliminated
            )
            name = f"{seat_table.number}" + ("  (you)" if yours else "")
            cells = (
                name,
                str(len(stacks)),
                format_chips(max(stacks, default=0)),
                format_chips(min(stacks, default=0)),
            )
            fill_row(table, row, cells, YOU_COLOR if yours else None)

        table.selectRow(min(selected, len(tournament.tables) - 1))
        table.blockSignals(False)
        self._show_selected_table()

    def _show_selected_table(self) -> None:
        tournament = self.tournament

        if tournament is None or not tournament.tables:
            return

        row = self._selected_table_row()
        seat_table = tournament.tables[min(row, len(tournament.tables) - 1)]
        big_blind = tournament.level.big_blind
        players = [p for p in seat_table.session.players if not p.is_eliminated]
        dealer = seat_table.session.table.dealer
        table = self.seats_table
        table.setRowCount(len(players))

        for index, player in enumerate(players):
            seat = str(index + 1) + ("  (button)" if player is dealer else "")
            cells = (seat, player.name, stack_text(player.stack, big_blind))
            fill_row(table, index, cells, self._color(player))

        # Your own table is the one you play; the others can be watched live.
        self.watch_button.setEnabled(tournament.live and seat_table.number != 1)

    def _watch_selected(self) -> None:
        tournament = self.tournament

        if tournament is None or not tournament.tables or not tournament.live:
            return

        row = min(self._selected_table_row(), len(tournament.tables) - 1)
        number = tournament.tables[row].number

        if number != 1:
            self.watch_requested.emit(number)

    def _selected_table_row(self) -> int:
        rows = {index.row() for index in self.tables_table.selectedIndexes()}

        return min(rows, default=0)

    def _filter_players(self) -> None:
        text = self.search_edit.text().strip().casefold()
        table = self.players_table

        for row in range(table.rowCount()):
            item = table.item(row, 1)
            name = item.text().casefold() if item is not None else ""
            table.setRowHidden(row, bool(text) and text not in name)

    def _color(self, player: Player) -> str | None:
        return YOU_COLOR if player.name == self.human_name else None

    def closeEvent(self, event: QCloseEvent) -> None:
        self._clock_timer.stop()
        super().closeEvent(event)
