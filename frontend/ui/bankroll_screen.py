"""The Bankroll screen: balance, results, graph and the ledger."""

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.application.bankroll import (
    DEFAULT_BALANCE,
    MODE_LABELS,
    TRANSACTION_LABELS,
    Bankroll,
    GameMode,
    Transaction,
)
from frontend.components.line_chart import LineChart
from frontend.formatting import format_chips

ADJUSTMENTS = "adjustments"
FILTERS: tuple[tuple[str, GameMode | str | None], ...] = (
    ("All", None),
    *((label, mode) for mode, label in MODE_LABELS.items()),
    ("Adjustments", ADJUSTMENTS),
)
COLUMNS = ("Date", "Type", "Mode", "Amount", "Balance", "Description")
MAX_BALANCE = 1_000_000_000


def signed(amount: int) -> str:
    return ("+" if amount > 0 else "") + format_chips(amount)


def ask_balance(parent: QWidget, current: int) -> int | None:
    value, accepted = QInputDialog.getInt(
        parent, "Set bankroll", "New bankroll:", current, 0, MAX_BALANCE, 1000
    )

    return value if accepted else None


def confirm_reset(parent: QWidget) -> bool:
    answer = QMessageBox.question(
        parent,
        "Reset bankroll",
        f"Reset your bankroll to {format_chips(DEFAULT_BALANCE)}? "
        "The ledger keeps a record of it.",
    )

    return answer == QMessageBox.StandardButton.Yes


class BankrollScreen(QWidget):
    """Shows the bankroll; Set and Reset are recorded as adjustments."""

    back_requested = Signal()
    changed = Signal()
    """Emitted after the bankroll or the hints setting changed (to save it)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.bankroll = Bankroll()
        self.ask_balance: Callable[[QWidget, int], int | None] = ask_balance
        self.confirm_reset: Callable[[QWidget], bool] = confirm_reset
        """Dialogs, replaced in tests."""

        title = QLabel("BANKROLL")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.balance_label = QLabel()
        self.balance_label.setObjectName("subtitle")
        self.balance_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_label = QLabel()
        self.results_label.setObjectName("statusText")
        self.results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.chart = LineChart()
        self.chart.x_label = "Transactions"
        self.chart.y_label = "Bankroll"
        self.chart.point_label = "Transaction"
        self.chart.include_zero = False
        self.chart.signed_values = False

        self.filter_combo = QComboBox()

        for label, value in FILTERS:
            self.filter_combo.addItem(label, value)

        self.filter_combo.currentIndexChanged.connect(self._fill_table)
        self.hints_check = QCheckBox("Bankroll-management hints on setup screens")
        self.hints_check.toggled.connect(self.changed)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch
        )

        self.set_button = QPushButton("Set bankroll…")
        self.set_button.clicked.connect(self._on_set_clicked)
        self.reset_button = QPushButton(f"Reset to {format_chips(DEFAULT_BALANCE)}")
        self.reset_button.clicked.connect(self._on_reset_clicked)
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.back_requested)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Show"))
        filters.addWidget(self.filter_combo)
        filters.addStretch()
        filters.addWidget(self.hints_check)

        buttons = QHBoxLayout()
        buttons.addWidget(self.set_button)
        buttons.addWidget(self.reset_button)
        buttons.addStretch()
        buttons.addWidget(self.back_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.addWidget(title)
        layout.addWidget(self.balance_label)
        layout.addWidget(self.results_label)
        layout.addWidget(self.chart, stretch=2)
        layout.addLayout(filters)
        layout.addWidget(self.table, stretch=3)
        layout.addLayout(buttons)

    @property
    def hints_enabled(self) -> bool:
        return self.hints_check.isChecked()

    def show_bankroll(self, bankroll: Bankroll, hints_enabled: bool) -> None:
        self.bankroll = bankroll
        self.hints_check.blockSignals(True)
        self.hints_check.setChecked(hints_enabled)
        self.hints_check.blockSignals(False)
        self.refresh()

    def refresh(self) -> None:
        bankroll = self.bankroll
        self.balance_label.setText(f"Balance: {format_chips(bankroll.balance)}")
        results = [f"Net result {signed(bankroll.net_result())}"]
        results += [
            f"{label} {signed(bankroll.net_result(mode))}"
            for mode, label in MODE_LABELS.items()
        ]
        self.results_label.setText("   ·   ".join(results))
        self.chart.set_series(
            ["Bankroll"],
            [
                (index, (value,))
                for index, value in enumerate(bankroll.balance_history())
            ],
        )
        self._fill_table()

    def visible_transactions(self) -> list[Transaction]:
        """The ledger, most recent first, filtered by the chosen mode."""
        wanted = self.filter_combo.currentData()
        rows = reversed(self.bankroll.transactions)

        if wanted is None:
            return list(rows)

        if wanted == ADJUSTMENTS:
            return [t for t in rows if t.mode is None]

        return [t for t in rows if t.mode == wanted]

    def _fill_table(self) -> None:
        transactions = self.visible_transactions()
        self.table.setRowCount(len(transactions))

        for row, transaction in enumerate(transactions):
            mode = MODE_LABELS[transaction.mode] if transaction.mode else "—"
            values = (
                transaction.time.replace("T", " "),
                TRANSACTION_LABELS[transaction.type],
                mode,
                signed(transaction.amount),
                format_chips(transaction.balance_after),
                transaction.description,
            )

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)

                if column in (3, 4):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )

                self.table.setItem(row, column, item)

        self.table.resizeColumnsToContents()

    def _on_set_clicked(self) -> None:
        value = self.ask_balance(self, self.bankroll.balance)

        if value is None or value == self.bankroll.balance:
            return

        self.bankroll.set_balance(value)
        self.refresh()
        self.changed.emit()

    def _on_reset_clicked(self) -> None:
        if not self.confirm_reset(self):
            return

        self.bankroll.reset()
        self.refresh()
        self.changed.emit()
