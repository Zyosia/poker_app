"""The equity calculator (V1.1): win chances of hands on any board.

Each hand is typed as two cards ("AsKd", "A♠ K♦", "10h 9h") or left empty
for a random hand. Every board is counted when every hand is known and there
are few enough boards (always from the flop on); otherwise random boards are
drawn (Monte Carlo). The counting runs in small steps on a timer, so the
screen stays responsive and the numbers refine as it goes.
"""

import random

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from backend.application.equity import EquityCalculator, EquityResult
from backend.poker_engine.constants import MAX_TABLE_SEATS, Card
from frontend.components.card_widget import CardWidget
from frontend.formatting import parse_cards

CARD_SIZE = QSize(40, 56)
MIN_HANDS = 2
DEFAULT_HANDS = 2
MONTE_CARLO_BOARDS = 60_000
"""Random boards drawn for an estimate (about ±0.4% on each equity)."""
EVALUATIONS_PER_TICK = 4_000
"""Hand evaluations per timer tick (about 40 ms), so the screen never stalls."""
RANDOM_CARD = "AS"
"""Any card: a random hand is drawn face down."""


class CardPreview(QWidget):
    """The cards typed in a field, drawn as cards."""

    def __init__(self, count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.card_widgets = [CardWidget(CARD_SIZE, self) for _ in range(count)]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        for widget in self.card_widgets:
            layout.addWidget(widget)

    def show_cards(self, cards: tuple[Card, ...], face_down: bool = False) -> None:
        for index, widget in enumerate(self.card_widgets):
            if face_down:
                widget.set_card(RANDOM_CARD, face_up=False)
            else:
                widget.set_card(cards[index] if index < len(cards) else None)


class HandRow:
    """The widgets of one hand: its cards and its results."""

    def __init__(self) -> None:
        self.label = QLabel()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Random hand")
        self.edit.setFixedWidth(170)
        self.preview = CardPreview(2)
        self.equity_label = QLabel("—")
        self.equity_label.setObjectName("resultText")
        self.win_label = QLabel("—")
        self.tie_label = QLabel("—")
        self.remove_button = QPushButton("✕")
        self.remove_button.setObjectName("small")
        self.remove_button.setToolTip("Remove this hand")

    @property
    def widgets(self) -> tuple[QWidget, ...]:
        return (
            self.label,
            self.edit,
            self.preview,
            self.equity_label,
            self.win_label,
            self.tie_label,
            self.remove_button,
        )

    def clear_results(self) -> None:
        for label in (self.equity_label, self.win_label, self.tie_label):
            label.setText("—")


class EquityScreen(QWidget):
    """Type hands and a board, and see each hand's chances."""

    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.seed: int | None = None
        """The seed of the random boards; None draws a new one each time."""
        self.calculator: EquityCalculator | None = None
        self._target_boards = 0
        self._chunk = 0

        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._on_tick)

        title = QLabel("EQUITY CALCULATOR")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel(
            "Two cards per hand (As Kd, A♠K♦, 10h 9h), or leave a hand empty "
            "for a random one. The board can have 0 to 5 cards."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        self.rows: list[HandRow] = []
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(8)

        for column, header in enumerate(("", "Cards", "", "Equity", "Win", "Tie")):
            label = QLabel(header)
            label.setObjectName("sectionTitle")
            self.grid.addWidget(label, 0, column)

        self.board_edit = QLineEdit()
        self.board_edit.setPlaceholderText("e.g. Qs Jh 2c — empty: before the flop")
        self.board_edit.setMaximumWidth(260)
        self.board_edit.textChanged.connect(self._on_input_changed)
        self.board_edit.returnPressed.connect(self.calculate)
        self.board_preview = CardPreview(5)

        self.add_button = QPushButton("Add a hand")
        self.add_button.clicked.connect(self.add_hand)
        self.calculate_button = QPushButton("Calculate")
        self.calculate_button.setObjectName("primary")
        self.calculate_button.clicked.connect(self.calculate)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear)
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self._on_back_clicked)

        self.status_label = QLabel()
        self.status_label.setObjectName("statusText")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label = QLabel()
        self.error_label.setObjectName("errorText")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        board = QHBoxLayout()
        board.addStretch()
        board_title = QLabel("Board")
        board_title.setObjectName("sectionTitle")
        board.addWidget(board_title)
        board.addWidget(self.board_edit)
        board.addWidget(self.board_preview)
        board.addStretch()

        hands = QHBoxLayout()
        hands.addStretch()
        hands.addLayout(self.grid)
        hands.addStretch()

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addStretch()
        buttons.addWidget(self.clear_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.calculate_button)
        buttons.addWidget(self.back_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(16)
        layout.addLayout(board)
        layout.addSpacing(12)
        layout.addLayout(hands)
        layout.addStretch()
        layout.addWidget(self.status_label)
        layout.addWidget(self.error_label)
        layout.addLayout(buttons)

        for _ in range(DEFAULT_HANDS):
            self.add_hand()

        self._update_buttons()

    # --- Hands ---------------------------------------------------------------

    def add_hand(self) -> None:
        if len(self.rows) >= MAX_TABLE_SEATS:
            return

        row = HandRow()
        row.edit.textChanged.connect(self._on_input_changed)
        row.edit.returnPressed.connect(self.calculate)
        row.remove_button.clicked.connect(lambda: self.remove_hand(row))
        self.rows.append(row)
        self._layout_rows()
        self._on_input_changed()

    def remove_hand(self, row: HandRow) -> None:
        if len(self.rows) <= MIN_HANDS:
            return

        self.rows.remove(row)

        for widget in row.widgets:
            self.grid.removeWidget(widget)
            widget.deleteLater()

        self._layout_rows()
        self._on_input_changed()

    def _layout_rows(self) -> None:
        for index, row in enumerate(self.rows, start=1):
            row.label.setText(f"Hand {index}")

            for column, widget in enumerate(row.widgets):
                self.grid.addWidget(widget, index, column)

    def set_hands(self, hands: list[str], board: str = "") -> None:
        """Type hands (one text per hand) and a board, as the user would."""
        while len(self.rows) < len(hands):
            self.add_hand()

        while len(self.rows) > max(MIN_HANDS, len(hands)):
            self.remove_hand(self.rows[-1])

        for row, text in zip(self.rows, hands, strict=False):
            row.edit.setText(text)

        self.board_edit.setText(board)

    # --- Input ---------------------------------------------------------------

    def _read_input(self) -> tuple[list[tuple[Card, ...] | None], tuple[Card, ...]]:
        """The hands (None: random) and the board; raises ValueError."""
        hands: list[tuple[Card, ...] | None] = []

        for index, row in enumerate(self.rows, start=1):
            cards = parse_cards(row.edit.text())

            if cards and len(cards) != 2:
                raise ValueError(f"Hand {index}: two cards, or none for a random hand.")

            hands.append(cards or None)

        board = parse_cards(self.board_edit.text())

        if len(board) > 5:
            raise ValueError("The board has at most five cards.")

        return hands, board

    def _on_input_changed(self) -> None:
        """Draw the cards typed so far; a change makes the results stale."""
        self.stop()
        self.calculator = None
        self.status_label.setText("")
        self.error_label.setText("")

        for row in self.rows:
            row.clear_results()

            try:
                cards = parse_cards(row.edit.text())
            except ValueError:
                cards = ()

            row.preview.show_cards(cards[:2], face_down=not row.edit.text().strip())

        try:
            board = parse_cards(self.board_edit.text())
        except ValueError:
            board = ()

        self.board_preview.show_cards(board[:5])
        self.add_button.setEnabled(len(self.rows) < MAX_TABLE_SEATS)

        for row in self.rows:
            row.remove_button.setEnabled(len(self.rows) > MIN_HANDS)

        self._update_buttons()

    # --- Calculation ---------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._timer.isActive()

    def calculate(self) -> None:
        self.stop()
        self.error_label.setText("")

        try:
            hands, board = self._read_input()
            seed = self.seed if self.seed is not None else random.getrandbits(32)
            calculator = EquityCalculator(hands, board, seed=seed)
        except ValueError as error:
            self.calculator = None
            self.error_label.setText(str(error))
            return

        self.calculator = calculator
        self._target_boards = calculator.total_boards or MONTE_CARLO_BOARDS
        self._chunk = max(1, EVALUATIONS_PER_TICK // len(hands))
        self._timer.start()
        self._update_buttons()

    def run_to_end(self) -> None:
        """Finish the calculation at once (tests)."""
        while self.is_running:
            self._on_tick()

    def stop(self) -> None:
        self._timer.stop()
        self._update_buttons()

    def _on_tick(self) -> None:
        calculator = self.calculator

        if calculator is None:
            self.stop()
            return

        remaining = self._target_boards - calculator.boards
        calculator.run(min(self._chunk, remaining))
        self._show_result(calculator.result())

        if calculator.boards >= self._target_boards or calculator.finished:
            self.stop()

    def _show_result(self, result: EquityResult) -> None:
        for index, row in enumerate(self.rows):
            margin = result.margins[index] if result.margins else None
            equity = f"{result.equity[index]:.1%}"
            row.equity_label.setText(
                equity if margin is None else f"{equity} ± {margin:.1%}"
            )
            row.win_label.setText(f"{result.wins[index]:.1%}")
            row.tie_label.setText(f"{result.ties[index]:.1%}")

        boards = f"{result.boards:,}".replace(",", " ")

        if result.exact:
            total = f"{self._target_boards:,}".replace(",", " ")
            self.status_label.setText(f"Exact: {boards} of {total} boards counted")
        else:
            self.status_label.setText(
                f"Estimate: {boards} random boards (Monte Carlo, 95% margins)"
            )

    def clear(self) -> None:
        self.set_hands(["", ""])

    def _update_buttons(self) -> None:
        running = self._timer.isActive()
        self.stop_button.setEnabled(running)
        self.calculate_button.setEnabled(not running)

    def _on_back_clicked(self) -> None:
        self.stop()
        self.back_requested.emit()
