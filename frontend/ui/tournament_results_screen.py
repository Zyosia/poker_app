"""Final standings of a tournament you played, with your stats."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.application.hand_summary import PlayerSummary, summarize_player
from backend.application.tournament import Tournament

from .tournament_screen import ordinal

STANDINGS_HEADERS = ("Place", "Player", "Prize", "Profit", "Out on hand", "Rebuys")


def format_share(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def summary_lines(summary: PlayerSummary) -> list[str]:
    return [
        f"Hands played: {summary.hands_dealt}",
        f"Hands won: {summary.hands_won}",
        f"VPIP: {format_share(summary.vpip)}   ·   PFR: {format_share(summary.pfr)}",
        f"Showdowns: {summary.showdowns} (won {summary.showdowns_won})",
        f"All-ins: {summary.all_ins}",
        f"Biggest pot won: {summary.biggest_pot_won}",
    ]


class TournamentResultsScreen(QWidget):
    play_again_requested = Signal()
    menu_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.title_label = QLabel("RESULTS")
        self.title_label.setObjectName("title")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.outcome_label = QLabel()
        self.outcome_label.setObjectName("subtitle")
        self.outcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.outcome_label.setWordWrap(True)

        self.standings_table = QTableWidget()
        self.standings_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.standings_table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.standings_table.verticalHeader().setVisible(False)
        self.standings_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.stats_label = QLabel()
        self.stats_label.setObjectName("summaryText")
        self.stats_label.setWordWrap(True)

        self.play_again_button = QPushButton("Play again")
        self.play_again_button.setObjectName("primary")
        self.play_again_button.clicked.connect(self.play_again_requested)
        self.menu_button = QPushButton("Back to menu")
        self.menu_button.clicked.connect(self.menu_requested)

        stats_title = QLabel("YOUR TOURNAMENT")
        stats_title.setObjectName("sectionTitle")
        stats_panel = QFrame()
        stats_panel.setObjectName("panel")
        stats_panel.setFixedWidth(300)
        stats_layout = QVBoxLayout(stats_panel)
        stats_layout.setContentsMargins(18, 14, 18, 14)
        stats_layout.addWidget(stats_title)
        stats_layout.addWidget(self.stats_label)
        stats_layout.addStretch()

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self.standings_table, stretch=1)
        body.addWidget(stats_panel)

        buttons = QHBoxLayout()
        buttons.addStretch()

        for button in (self.menu_button, self.play_again_button):
            button.setMinimumSize(160, 46)
            buttons.addWidget(button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 20, 32, 24)
        layout.setSpacing(12)
        layout.addWidget(self.title_label)
        layout.addWidget(self.outcome_label)
        layout.addLayout(body, stretch=1)
        layout.addLayout(buttons)

    def show_tournament(self, tournament: Tournament, human_name: str) -> None:
        result = tournament.result
        you = result.finish_of(human_name)
        kind = "SPIN & GO" if result.multiplier is not None else "TOURNAMENT"
        self.title_label.setText(f"{kind} RESULTS")

        outcome = f"You finished {ordinal(you.place)}"
        outcome += f" and won {you.prize}" if you.prize else ""
        details = [
            f"prize pool {result.prize_pool}",
            f"{result.hands_played} hands",
            f"level {result.level_index + 1} ({result.level.describe()})",
        ]

        if result.multiplier is not None:
            details.insert(0, f"multiplier × {result.multiplier}")

        if result.capped:
            details.append("stopped by the hand limit")

        self.outcome_label.setText(f"{outcome}.   {'   ·   '.join(details)}")
        self._fill_standings(tournament, human_name)
        summary = summarize_player(tournament.session.hands, human_name)
        profit = you.profit
        lines = [f"Invested: {you.invested}   ·   Profit: {profit:+}", ""]
        self.stats_label.setText("\n".join(lines + summary_lines(summary)))

    def _fill_standings(self, tournament: Tournament, human_name: str) -> None:
        finishes = tournament.result.finishes
        table = self.standings_table
        table.clear()
        table.setColumnCount(len(STANDINGS_HEADERS))
        table.setRowCount(len(finishes))
        table.setHorizontalHeaderLabels(STANDINGS_HEADERS)

        for row, finish in enumerate(finishes):
            out = (
                "—"
                if finish.eliminated_on_hand is None
                else str(finish.eliminated_on_hand)
            )
            rebuys = (
                f"{finish.rebuys} + {finish.add_ons} add-on"
                if finish.add_ons
                else str(finish.rebuys)
            )
            cells = (
                ordinal(finish.place),
                finish.name + ("  (you)" if finish.name == human_name else ""),
                str(finish.prize),
                f"{finish.profit:+}",
                out,
                rebuys,
            )

            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, column, item)
