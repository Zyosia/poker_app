"""Results of a Bot Arena run: ranking, chip graph, summary and details."""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from backend.bots.factory import BOT_TYPES
from backend.simulation.config import StackPolicy
from backend.simulation.result import SimulationResult
from backend.simulation.stats import ACTION_CATEGORIES, STREETS, PlayerStats
from backend.simulation.summary import summarize
from frontend.components.line_chart import LineChart


def format_percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def format_decimal(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def format_chips(value: int) -> str:
    return f"{value:+,}".replace(",", " ")


class SortableItem(QTableWidgetItem):
    """A table cell displaying text but sorted by a number."""

    def __init__(self, text: str, sort_value: float | None) -> None:
        super().__init__(text)
        self.sort_value = float("-inf") if sort_value is None else sort_value
        self.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, SortableItem):
            return self.sort_value < other.sort_value

        return super().__lt__(other)


Column = tuple[str, Callable[[PlayerStats], tuple[str, float | None]]]


def ranking_columns(result: SimulationResult) -> list[Column]:
    """The columns of the ranking table, with their display and sort values."""
    big_blind = result.config.big_blind

    def win_rate(stats: PlayerStats) -> tuple[str, float | None]:
        rate = stats.bb_per_100(big_blind)
        interval = stats.confidence_interval_bb_per_100(big_blind)

        if rate is None:
            return "—", None

        if interval is None:
            return f"{rate:+.1f}", rate

        return f"{rate:+.1f} ±{(interval[1] - interval[0]) / 2:.1f}", rate

    def percent(
        value: Callable[[PlayerStats], float | None],
    ) -> Callable[[PlayerStats], tuple[str, float | None]]:
        return lambda stats: (format_percent(value(stats)), value(stats))

    columns: list[Column] = [
        ("Player", lambda s: (s.name, None)),
        ("Style", lambda s: (BOT_TYPES[s.bot].label, None)),
        ("Hands", lambda s: (f"{s.hands:,}".replace(",", " "), s.hands)),
        ("bb/100 (95% CI)", win_rate),
        ("Net chips", lambda s: (format_chips(s.net_chips), s.net_chips)),
        ("VPIP", percent(lambda s: s.vpip)),
        ("PFR", percent(lambda s: s.pfr)),
        ("AF", lambda s: (format_decimal(s.aggression_factor), s.aggression_factor)),
        ("WTSD", percent(lambda s: s.wtsd)),
        ("W$SD", percent(lambda s: s.wsd)),
    ]

    if result.config.stack_policy == StackPolicy.ELIMINATION:
        columns += [
            ("Win %", percent(lambda s: s.win_rate)),
            (
                "Avg finish",
                lambda s: (format_decimal(s.average_finish), s.average_finish),
            ),
        ]
    elif result.config.stack_policy == StackPolicy.AUTO_REBUY:
        columns.append(("Rebuys", lambda s: (str(s.rebuys), s.rebuys)))

    return columns


class ArenaResultsScreen(QWidget):
    """Displays a ``SimulationResult``."""

    back_requested = Signal()
    rerun_requested = Signal(object)
    """Emitted with the configuration to run again (same seed)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.result: SimulationResult | None = None

        self.title_label = QLabel("RESULTS")
        self.title_label.setObjectName("sectionTitle")
        self.summary_label = QLabel()
        self.summary_label.setObjectName("summaryText")
        self.summary_label.setWordWrap(True)

        self.ranking_table = self._make_table()
        self.ranking_table.setSortingEnabled(True)
        self.chart = LineChart()

        self.actions_table = self._make_table()
        self.positions_table = self._make_table()
        self.details_view = QPlainTextEdit()
        self.details_view.setReadOnly(True)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview(), "Overview")
        self.tabs.addTab(self._build_advanced(), "Advanced")

        self.export_json_button = QPushButton("Export JSON")
        self.export_json_button.clicked.connect(lambda: self._ask_export("json"))
        self.export_csv_button = QPushButton("Export CSV")
        self.export_csv_button.clicked.connect(lambda: self._ask_export("csv"))
        self.rerun_button = QPushButton("Run again (same seed)")
        self.rerun_button.setObjectName("accent")
        self.rerun_button.clicked.connect(self._on_rerun_clicked)
        self.back_button = QPushButton("Back to setup")
        self.back_button.setObjectName("primary")
        self.back_button.clicked.connect(self.back_requested)

        buttons = QHBoxLayout()
        buttons.addWidget(self.export_json_button)
        buttons.addWidget(self.export_csv_button)
        buttons.addStretch()
        buttons.addWidget(self.rerun_button)
        buttons.addWidget(self.back_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(self.title_label)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.tabs, stretch=1)
        layout.addLayout(buttons)

    @staticmethod
    def _make_table() -> QTableWidget:
        table = QTableWidget()
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setStretchLastSection(True)

        return table

    def _build_overview(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        self.ranking_table.setMaximumHeight(230)
        layout.addWidget(self.ranking_table)
        layout.addWidget(self.chart, stretch=1)

        return page

    def _build_advanced(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)

        tables = QVBoxLayout()

        for title, table in (
            ("ACTION FREQUENCIES PER STREET", self.actions_table),
            ("RESULTS BY POSITION (bb/100)", self.positions_table),
        ):
            label = QLabel(title)
            label.setObjectName("sectionTitle")
            tables.addWidget(label)
            tables.addWidget(table, stretch=1)

        layout.addLayout(tables, stretch=3)
        layout.addWidget(self.details_view, stretch=2)

        return page

    # --- Display -------------------------------------------------------------

    def show_result(self, result: SimulationResult) -> None:
        self.result = result
        config = result.config
        policy = config.stack_policy.value
        self.title_label.setText(
            f"RESULTS   ·   {result.totals.hands:,} HANDS   ·   SEED {config.seed}"
            f"   ·   {policy.upper()}"
            + ("   ·   DUPLICATE" if config.duplicate else "")
        )
        self.summary_label.setText(" ".join(summarize(result)))

        self._fill_ranking(result)
        self.chart.set_series(list(result.players), result.chart)
        self._fill_actions(result)
        self._fill_positions(result)
        self.details_view.setPlainText(self._details_text(result))
        self.tabs.setCurrentIndex(0)

    def _fill_ranking(self, result: SimulationResult) -> None:
        columns = ranking_columns(result)
        ranking = result.ranking()
        table = self.ranking_table
        table.setSortingEnabled(False)
        table.clear()
        table.setColumnCount(len(columns))
        table.setRowCount(len(ranking))
        table.setHorizontalHeaderLabels([name for name, _ in columns])

        for row, stats in enumerate(ranking):
            for column, (_, value) in enumerate(columns):
                text, sort_value = value(stats)
                table.setItem(row, column, SortableItem(text, sort_value))

        table.setSortingEnabled(True)

    def _fill_actions(self, result: SimulationResult) -> None:
        table = self.actions_table
        headers = [
            "Player",
            "Street",
            *(c.replace("_", "-") for c in ACTION_CATEGORIES),
        ]
        rows = [
            (stats, street) for stats in result.players.values() for street in STREETS
        ]
        table.clear()
        table.setColumnCount(len(headers))
        table.setRowCount(len(rows))
        table.setHorizontalHeaderLabels(headers)

        for row, (stats, street) in enumerate(rows):
            frequencies = stats.action_frequencies(street)
            cells = [stats.name, street.title()]
            cells += [format_percent(frequencies[c]) for c in ACTION_CATEGORIES]

            for column, text in enumerate(cells):
                table.setItem(row, column, SortableItem(text, None))

    def _fill_positions(self, result: SimulationResult) -> None:
        big_blind = result.config.big_blind
        positions = sorted(
            {
                position
                for stats in result.players.values()
                for position in stats.positions
            }
        )
        table = self.positions_table
        table.clear()
        table.setColumnCount(len(positions) + 1)
        table.setRowCount(len(result.players))
        table.setHorizontalHeaderLabels(["Player", *positions])

        for row, stats in enumerate(result.players.values()):
            table.setItem(row, 0, SortableItem(stats.name, None))

            for column, position in enumerate(positions, start=1):
                position_result = stats.positions.get(position)
                text = "—"

                if position_result is not None and position_result.hands:
                    rate = position_result.net_chips / big_blind / position_result.hands
                    text = f"{rate * 100:+.1f}  ({position_result.hands:,})".replace(
                        ",", " "
                    )

                table.setItem(row, column, SortableItem(text, None))

    @staticmethod
    def _details_text(result: SimulationResult) -> str:
        config = result.config
        engine = result.engine
        lines = [
            f"Seed: {config.seed}",
            f"Hands: {result.totals.hands:,}",
            f"Stack policy: {config.stack_policy.value}",
            f"Blinds: {config.small_blind}/{config.big_blind}, "
            f"stack {config.starting_stack:,}",
            f"Batch size: {config.batch_size} ({result.batch_count} batches)",
            f"Workers: {config.workers}",
            f"Duplicate: {f'yes, {config.deals} deals' if config.duplicate else 'no'}",
            f"Duration: {result.duration_seconds:.1f} s "
            f"({result.hands_per_second:,.0f} hands/s)",
        ]

        if config.stack_policy == StackPolicy.ELIMINATION:
            lines.append(
                f"Sessions: {result.totals.sessions} "
                f"(capped: {result.totals.capped_sessions})"
            )

        lines += [
            "",
            "ENGINE LAB",
            f"Showdowns: {format_percent(engine.showdown_frequency)}",
            f"Split pots: {format_decimal((engine.split_pot_frequency or 0) * 100)} %",
            f"All-in hands: {format_percent(engine.all_in_frequency)}",
            f"Auto run-outs: {format_percent(engine.runout_frequency)}",
            "Side pots at showdown: "
            + (
                ", ".join(
                    f"{count}: {hands:,}"
                    for count, hands in sorted(engine.side_pot_counts.items())
                )
                or "—"
            ),
            "",
            "SHOWDOWN HANDS",
        ]
        lines += [
            f"{category.replace('_', ' ').title():<18}"
            f"{format_decimal((frequency or 0) * 100)} %"
            for category, frequency in engine.category_frequencies().items()
        ]

        return "\n".join(lines)

    # --- Actions -------------------------------------------------------------

    def export(self, path: Path, kind: str) -> Path:
        """Export the result as JSON or CSV."""
        if self.result is None:
            raise RuntimeError("No result to export.")

        if kind == "json":
            return self.result.save_json(path)

        return self.result.save_csv(path)

    def _ask_export(self, kind: str) -> None:
        if self.result is None:
            return

        name = f"arena-{self.result.config.seed}.{kind}"
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {kind.upper()}", name, f"{kind.upper()} (*.{kind})"
        )

        if path:
            saved = self.export(Path(path), kind)
            self.title_label.setText(
                f"{self.title_label.text()}   ·   SAVED {saved.name}"
            )

    def _on_rerun_clicked(self) -> None:
        if self.result is not None:
            self.rerun_requested.emit(self.result.config)
