"""My stats (V1.1): your playing stats and results across saved sessions."""

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.application.game_modes import MODE_LABELS
from backend.application.hand_records import LibraryScan, SessionRecord
from backend.poker_engine.constants import Position
from backend.simulation.my_stats import (
    CashResults,
    MyStats,
    TournamentResults,
    compute_my_stats,
)
from backend.simulation.stats import PlayerStats

from .arena_results_screen import format_decimal, format_percent

TENDENCY_COLUMNS = ("Stat", "You", "Counted", "What it measures")
POSITION_COLUMNS = ("Position", "Hands", "Net chips", "bb/100")
POSITION_ORDER = tuple(Position)

Tendency = tuple[str, Callable[[PlayerStats], str], Callable[[PlayerStats], str], str]
TENDENCIES: tuple[Tendency, ...] = (
    (
        "VPIP",
        lambda s: format_percent(s.vpip),
        lambda s: f"{s.vpip_hands} / {s.hands}",
        "Hands where you put chips in voluntarily before the flop.",
    ),
    (
        "PFR",
        lambda s: format_percent(s.pfr),
        lambda s: f"{s.pfr_hands} / {s.hands}",
        "Hands you raised before the flop.",
    ),
    (
        "3-bet",
        lambda s: format_percent(s.three_bet),
        lambda s: f"{s.three_bets} / {s.three_bet_opportunities}",
        "Re-raises when facing a single raise before the flop.",
    ),
    (
        "Aggression factor",
        lambda s: format_decimal(s.aggression_factor),
        lambda s: f"{s.postflop_aggressive_actions} / {s.postflop_calls}",
        "After the flop: bets and raises per call.",
    ),
    (
        "Aggression frequency",
        lambda s: format_percent(s.aggression_frequency),
        lambda s: f"{s.postflop_aggressive_actions} actions",
        "After the flop: bets and raises among bets, raises, calls and folds.",
    ),
    (
        "Flops seen",
        lambda s: format_percent(s.saw_flop / s.hands if s.hands else None),
        lambda s: f"{s.saw_flop} / {s.hands}",
        "Hands where you saw the flop.",
    ),
    (
        "WTSD",
        lambda s: format_percent(s.wtsd),
        lambda s: f"{s.went_to_showdown} / {s.saw_flop}",
        "Flops seen that went to showdown.",
    ),
    (
        "W$SD",
        lambda s: format_percent(s.wsd),
        lambda s: f"{s.won_at_showdown} / {s.went_to_showdown}",
        "Showdowns where you won chips.",
    ),
    (
        "C-bet",
        lambda s: format_percent(s.cbet),
        lambda s: f"{s.cbets} / {s.cbet_opportunities}",
        "Flops you bet as the pre-flop raiser, when checked to.",
    ),
    (
        "Fold to c-bet",
        lambda s: format_percent(s.fold_to_cbet),
        lambda s: f"{s.folds_to_cbet} / {s.fold_to_cbet_opportunities}",
        "Continuation bets you folded to.",
    ),
)


def signed(value: float, unit: str = "") -> str:
    text = f"{value:+,.0f}".replace(",", " ") if value else "0"

    return f"{text}{unit}"


def cash_text(cash: CashResults) -> str:
    if cash.hands == 0:
        return "Cash games: no hand yet."

    rate = cash.bb_per_100
    interval = cash.confidence_interval
    text = f"Cash games: {signed(cash.net_chips)} chips over {cash.hands} hands"

    if rate is not None:
        text += f"   ·   {rate:+.1f} bb/100"

    if interval is not None:
        text += f" (95%: {interval[0]:+.0f} to {interval[1]:+.0f})"

    return text


def tournament_text(label: str, results: TournamentResults) -> str:
    if results.played == 0 and results.unfinished == 0:
        return f"{label}: none yet."

    parts = [f"{label}: {results.played} played"]

    if results.played:
        itm = format_percent(results.itm)
        roi = "—" if results.roi is None else f"{results.roi:+.0%}"
        parts += [
            f"{results.wins} won",
            f"in the money {itm}",
            f"profit {signed(results.profit)}",
            f"ROI {roi}",
        ]

    if results.unfinished:
        parts.append(f"{results.unfinished} not finished")

    return "   ·   ".join(parts)


class MyStatsScreen(QWidget):
    """Your stats, computed from the saved sessions."""

    back_requested = Signal()
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sessions: tuple[SessionRecord, ...] = ()
        self.stats = MyStats()

        title = QLabel("MY STATS")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All modes", None)

        for mode, label in MODE_LABELS.items():
            self.filter_combo.addItem(label, mode)

        self.filter_combo.currentIndexChanged.connect(self._recompute)
        self.summary_label = QLabel()
        self.summary_label.setObjectName("subtitle")
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_label = QLabel()
        self.results_label.setObjectName("statusText")
        self.results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notice_label = QLabel()
        self.notice_label.setObjectName("errorText")
        self.notice_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.tendencies_table = self._table(TENDENCY_COLUMNS, len(TENDENCIES))
        positions_title = QLabel("CASH GAMES BY POSITION")
        positions_title.setObjectName("sectionTitle")
        self.positions_table = self._table(POSITION_COLUMNS, 0)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_requested)
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.back_requested)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Show"))
        filters.addWidget(self.filter_combo)
        filters.addStretch()

        positions = QVBoxLayout()
        positions.addWidget(positions_title)
        positions.addWidget(self.positions_table)

        tables = QHBoxLayout()
        tables.addWidget(self.tendencies_table, stretch=3)
        tables.addLayout(positions, stretch=2)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.back_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.addWidget(title)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.results_label)
        layout.addLayout(filters)
        layout.addLayout(tables, stretch=1)
        layout.addWidget(self.notice_label)
        layout.addLayout(buttons)

    @staticmethod
    def _table(columns: tuple[str, ...], rows: int) -> QTableWidget:
        table = QTableWidget(rows, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setStretchLastSection(True)

        return table

    def show_scan(self, scan: LibraryScan) -> None:
        """Compute the stats of the sessions found in the sessions folder."""
        self.sessions = scan.sessions
        count = len(scan.unreadable)
        self.notice_label.setText(
            f"{count} session file{'s' if count > 1 else ''} could not be read."
            if count
            else ""
        )
        self._recompute()

    def _recompute(self) -> None:
        self.stats = compute_my_stats(self.sessions, self.filter_combo.currentData())
        stats = self.stats

        if stats.hands == 0:
            self.summary_label.setText("No hand played yet: your stats start here.")
        else:
            self.summary_label.setText(
                f"{stats.sessions} sessions   ·   {stats.hands} hands"
            )

        self.results_label.setText(
            "\n".join(
                (
                    cash_text(stats.cash),
                    tournament_text("Tournaments", stats.tournaments),
                    tournament_text("Spin & Go", stats.spins),
                )
            )
        )
        self._fill_tendencies(stats.tendencies)
        self._fill_positions(stats.positions)

    def _fill_tendencies(self, tendencies: PlayerStats) -> None:
        for row, (name, value, counted, meaning) in enumerate(TENDENCIES):
            cells = (name, value(tendencies), counted(tendencies), meaning)

            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)

                if column in (1, 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                self.tendencies_table.setItem(row, column, item)

    def tendency(self, name: str) -> str:
        """The value shown for a stat (for example "VPIP")."""
        row = next(i for i, tendency in enumerate(TENDENCIES) if tendency[0] == name)

        item = self.tendencies_table.item(row, 1)
        assert item is not None

        return item.text()

    def _fill_positions(self, positions: dict[str, CashResults]) -> None:
        rows = [position for position in POSITION_ORDER if position in positions]
        self.positions_table.setRowCount(len(rows))

        for row, position in enumerate(rows):
            line = positions[position]
            rate = line.bb_per_100
            cells = (
                position.value,
                str(line.hands),
                signed(line.net_chips),
                "—" if rate is None else f"{rate:+.1f}",
            )

            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.positions_table.setItem(row, column, item)
