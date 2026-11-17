"""The equity calculator (V1.1, cards and ranges V1.1.1).

Each player holds a **hand** (two cards picked with the mouse, or none for a
random hand) or a **range** (starting hands painted on the 13 × 13 grid,
typed in notation such as "QQ+, AKs", or taken from a preset). The board has
0 to 5 cards. Every deal is counted when there are few enough; otherwise
random deals are drawn (Monte Carlo). The counting runs in small steps on a
timer, so the screen stays responsive and the numbers refine as it goes.
"""

import random

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.application.equity import EquityCalculator, EquityResult, PlayerHand
from backend.application.ranges import PRESET_RANGES, HandRange, preset_range
from backend.poker_engine.constants import MAX_TABLE_SEATS, Card
from frontend.components.card_picker import CardPicker, CardSlot
from frontend.components.range_grid import RangeGrid
from frontend.formatting import parse_cards

SLOT_SIZE = QSize(40, 56)
MIN_HANDS = 2
DEFAULT_HANDS = 2
BOARD_CARDS = 5
MONTE_CARLO_BOARDS = 60_000
"""Random deals drawn for an estimate (about ±0.4% on each equity)."""
EVALUATIONS_PER_TICK = 4_000
"""Hand evaluations per timer tick (about 40 ms), so the screen never stalls."""
HAND_MODE = "Hand"
RANGE_MODE = "Range"
PRESET_PROMPT = "Preset range…"


class PlayerRow:
    """The widgets of one player: a hand or a range, and the results."""

    def __init__(self) -> None:
        self.label = QLabel()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([HAND_MODE, RANGE_MODE])
        self.slots = [CardSlot(SLOT_SIZE) for _ in range(2)]
        self.range = HandRange(frozenset())
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("e.g. QQ+, AKs, A5s-A2s")
        self.range_edit.setFixedWidth(230)
        self.grid_button = QPushButton("Grid")
        self.grid_button.setObjectName("small")
        self.grid_button.setFixedWidth(56)
        self.grid_button.setToolTip("Paint the range on the grid of hands.")
        self.range_info = QLabel("0 combos")
        self.range_info.setObjectName("sectionTitle")

        hand_page = QWidget()
        hand_layout = QHBoxLayout(hand_page)
        hand_layout.setContentsMargins(0, 0, 0, 0)
        hand_layout.setSpacing(4)

        for slot in self.slots:
            hand_layout.addWidget(slot)

        hand_layout.addStretch()
        range_page = QWidget()
        range_layout = QVBoxLayout(range_page)
        range_layout.setContentsMargins(0, 0, 0, 0)
        range_layout.setSpacing(2)
        edit_row = QHBoxLayout()
        edit_row.addWidget(self.range_edit)
        edit_row.addWidget(self.grid_button)
        range_layout.addLayout(edit_row)
        range_layout.addWidget(self.range_info)
        self.content = QStackedWidget()
        self.content.addWidget(hand_page)
        self.content.addWidget(range_page)
        self.content.setFixedHeight(SLOT_SIZE.height() + 4)

        self.equity_label = QLabel("—")
        self.equity_label.setObjectName("resultText")
        self.win_label = QLabel("—")
        self.tie_label = QLabel("—")
        self.remove_button = QPushButton("✕")
        self.remove_button.setObjectName("small")
        self.remove_button.setToolTip("Remove this player")

    @property
    def widgets(self) -> tuple[QWidget, ...]:
        return (
            self.label,
            self.mode_combo,
            self.content,
            self.equity_label,
            self.win_label,
            self.tie_label,
            self.remove_button,
        )

    @property
    def is_range(self) -> bool:
        return self.mode_combo.currentText() == RANGE_MODE

    @property
    def cards(self) -> list[Card]:
        return [slot.card for slot in self.slots if slot.card is not None]

    def set_range(self, hand_range: HandRange) -> None:
        self.range = hand_range
        self.range_edit.setText(hand_range.notation)
        self.range_edit.setCursorPosition(0)
        self.range_edit.setToolTip(hand_range.notation)
        self.range_info.setText(
            f"{hand_range.combo_count} combos  ·  {hand_range.share:.1%}"
        )

    def clear_results(self) -> None:
        for label in (self.equity_label, self.win_label, self.tie_label):
            label.setText("—")


class EquityScreen(QWidget):
    """Choose hands, ranges and a board, and see each player's chances."""

    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.seed: int | None = None
        """The seed of the random deals; None draws a new one each time."""
        self.calculator: EquityCalculator | None = None
        self.active_slot: CardSlot | None = None
        self.range_row: PlayerRow | None = None
        """The player whose range the grid shows."""
        self._target = 0
        self._chunk = 0
        self._uses_ranges = False

        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._on_tick)

        title = QLabel("EQUITY CALCULATOR")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.rows: list[PlayerRow] = []
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(8)

        for column, header in enumerate(
            ("", "", "Hand or range", "Equity", "Win", "Tie")
        ):
            label = QLabel(header)
            label.setObjectName("sectionTitle")
            self.grid.addWidget(label, 0, column)

        self.board_slots = [CardSlot(SLOT_SIZE) for _ in range(BOARD_CARDS)]

        for slot in self.board_slots:
            self._connect_slot(slot)

        self.add_button = QPushButton("Add a player")
        self.add_button.clicked.connect(self.add_player)
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
        self.status_label.setWordWrap(True)
        self.error_label = QLabel()
        self.error_label.setObjectName("errorText")
        self.error_label.setWordWrap(True)

        self.picker = CardPicker()
        self.picker.card_chosen.connect(self._on_card_chosen)
        self.range_grid = RangeGrid()
        self.range_grid.changed.connect(self._on_grid_changed)
        self.range_title = QLabel()
        self.range_title.setObjectName("sectionTitle")
        self.preset_combo = QComboBox()
        self.preset_combo.addItem(PRESET_PROMPT)
        self.preset_combo.addItems(list(PRESET_RANGES))
        self.preset_combo.activated.connect(self._on_preset_chosen)
        self.clear_range_button = QPushButton("Clear range")
        self.clear_range_button.setObjectName("small")
        self.clear_range_button.clicked.connect(self._clear_range)
        self.done_button = QPushButton("Done")
        self.done_button.setObjectName("small")
        self.done_button.clicked.connect(self._show_picker)

        self.side_stack = QStackedWidget()
        self.side_stack.addWidget(self._picker_page())
        self.side_stack.addWidget(self._range_page())

        board = QHBoxLayout()
        board_title = QLabel("Board")
        board_title.setObjectName("sectionTitle")
        board.addWidget(board_title)

        for slot in self.board_slots:
            board.addWidget(slot)

        board.addStretch()

        buttons = QHBoxLayout()
        buttons.addWidget(self.add_button)
        buttons.addStretch()
        buttons.addWidget(self.clear_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.calculate_button)
        buttons.addWidget(self.back_button)

        left = QVBoxLayout()
        left.addLayout(board)
        left.addSpacing(10)
        players = QWidget()
        players.setLayout(self.grid)
        players.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        left.addWidget(players)
        left.addStretch()
        left.addWidget(self.status_label)
        left.addWidget(self.error_label)

        body = QHBoxLayout()
        body.addLayout(left, stretch=1)
        body.addSpacing(16)
        body.addWidget(self.side_stack)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 16)
        layout.addWidget(title)
        layout.addLayout(body, stretch=1)
        layout.addLayout(buttons)

        for _ in range(DEFAULT_HANDS):
            self.add_player()

        self._select(self.rows[0].slots[0])

    def _picker_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(
            "Click a card place, then a card. Right-click a place to empty it. "
            "A hand left empty is a random hand."
        )
        hint.setObjectName("sectionTitle")
        hint.setWordWrap(True)
        hint.setMaximumWidth(480)
        layout.addWidget(hint)
        layout.addWidget(self.picker)
        layout.addStretch()

        return page

    def _range_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.addWidget(self.range_title, stretch=1)
        top.addWidget(self.preset_combo)
        layout.addLayout(top)
        layout.addWidget(self.range_grid, stretch=1)
        bottom = QHBoxLayout()
        legend = QLabel("Pairs · suited above · offsuit below. Drag to paint.")
        legend.setObjectName("sectionTitle")
        bottom.addWidget(legend, stretch=1)
        bottom.addWidget(self.clear_range_button)
        bottom.addWidget(self.done_button)
        layout.addLayout(bottom)

        return page

    # --- Players ---------------------------------------------------------------

    def add_player(self) -> None:
        if len(self.rows) >= MAX_TABLE_SEATS:
            return

        row = PlayerRow()

        for slot in row.slots:
            self._connect_slot(slot)

        row.mode_combo.currentTextChanged.connect(lambda _text: self._on_mode(row))
        row.grid_button.clicked.connect(lambda: self._show_range(row))
        row.range_edit.editingFinished.connect(lambda: self._on_range_typed(row))
        row.remove_button.clicked.connect(lambda: self.remove_player(row))
        self.rows.append(row)
        self._layout_rows()
        self._changed()

    def remove_player(self, row: PlayerRow) -> None:
        if len(self.rows) <= MIN_HANDS:
            return

        if self.active_slot in row.slots:
            self._select(None)

        if self.range_row is row:
            self._show_picker()

        self.rows.remove(row)

        for widget in row.widgets:
            self.grid.removeWidget(widget)
            widget.deleteLater()

        self._layout_rows()
        self._changed()

    def _layout_rows(self) -> None:
        for index, row in enumerate(self.rows, start=1):
            row.label.setText(f"Player {index}")

            for column, widget in enumerate(row.widgets):
                self.grid.addWidget(widget, index, column)

    def set_hand(self, index: int, text: str) -> None:
        """Give a player two cards ("As Kd"), or none for a random hand."""
        row = self._row(index)
        row.mode_combo.setCurrentText(HAND_MODE)
        cards = parse_cards(text)

        for slot, card in zip(row.slots, [*cards, None, None], strict=False):
            slot.set_card(card)

        self._changed()

    def set_range(self, index: int, text: str) -> None:
        """Give a player a range written in notation ("QQ+, AKs")."""
        row = self._row(index)
        row.mode_combo.setCurrentText(RANGE_MODE)
        row.set_range(HandRange.parse(text))
        self._show_range(row)
        self._changed()

    def set_board(self, text: str) -> None:
        cards = parse_cards(text)

        for slot, card in zip(
            self.board_slots, [*cards, *[None] * BOARD_CARDS], strict=False
        ):
            slot.set_card(card)

        self._changed()

    def _row(self, index: int) -> PlayerRow:
        while len(self.rows) <= index:
            self.add_player()

        return self.rows[index]

    def clear(self) -> None:
        while len(self.rows) > MIN_HANDS:
            self.remove_player(self.rows[-1])

        for row in self.rows:
            row.mode_combo.setCurrentText(HAND_MODE)
            row.set_range(HandRange(frozenset()))

        for slot in self._all_slots():
            slot.set_card(None)

        self._show_picker()
        self._select(self.rows[0].slots[0])
        self._changed()

    # --- Cards -----------------------------------------------------------------

    def _connect_slot(self, slot: CardSlot) -> None:
        slot.clicked.connect(lambda: self._select(slot))
        slot.cleared.connect(lambda: self._clear_slot(slot))

    def _all_slots(self) -> list[CardSlot]:
        hands = [slot for row in self.rows if not row.is_range for slot in row.slots]

        return hands + self.board_slots

    def _select(self, slot: CardSlot | None) -> None:
        if self.active_slot is not None:
            self.active_slot.set_selected(False)

        self.active_slot = slot

        if slot is not None:
            slot.set_selected(True)
            self._show_picker()

    def _clear_slot(self, slot: CardSlot) -> None:
        slot.set_card(None)
        self._select(slot)
        self._changed()

    def _on_card_chosen(self, card: Card) -> None:
        slot = self.active_slot

        if slot is None:
            return

        slot.set_card(card)
        slots = self._all_slots()
        start = slots.index(slot) if slot in slots else 0
        following = slots[start + 1 :] + slots[: start + 1]
        self._select(next((s for s in following if s.card is None), slot))
        self._changed()

    # --- Ranges ----------------------------------------------------------------

    def _on_mode(self, row: PlayerRow) -> None:
        row.content.setCurrentIndex(1 if row.is_range else 0)

        if row.is_range:
            if self.active_slot in row.slots:
                self._select(None)

            self._show_range(row)
        elif self.range_row is row:
            self._show_picker()

        self._changed()

    def _show_range(self, row: PlayerRow) -> None:
        self.range_row = row
        index = self.rows.index(row) + 1
        self.range_title.setText(f"RANGE OF PLAYER {index}")
        self.range_grid.set_labels(row.range.labels)
        self.preset_combo.setCurrentIndex(0)
        self.side_stack.setCurrentIndex(1)

    def _show_picker(self) -> None:
        self.range_row = None
        self.side_stack.setCurrentIndex(0)

    def _on_grid_changed(self) -> None:
        if self.range_row is not None:
            self.range_row.set_range(HandRange(self.range_grid.labels()))
            self._changed()

    def _on_preset_chosen(self, index: int) -> None:
        if index > 0 and self.range_row is not None:
            hand_range = preset_range(self.preset_combo.itemText(index))
            self.range_row.set_range(hand_range)
            self.range_grid.set_labels(hand_range.labels)
            self._changed()

    def _clear_range(self) -> None:
        if self.range_row is not None:
            self.range_row.set_range(HandRange(frozenset()))
            self.range_grid.set_labels(())
            self._changed()

    def _on_range_typed(self, row: PlayerRow) -> None:
        try:
            hand_range = HandRange.parse(row.range_edit.text())
        except ValueError as error:
            self.error_label.setText(str(error))
            return

        row.set_range(hand_range)

        if self.range_row is row:
            self.range_grid.set_labels(hand_range.labels)

        self._changed()

    # --- Input -----------------------------------------------------------------

    def _changed(self) -> None:
        """A change: the cards used are dimmed, the results become stale."""
        self.stop()
        self.calculator = None
        self.status_label.setText("")
        self.error_label.setText("")
        used = [slot.card for slot in self._all_slots() if slot.card is not None]
        self.picker.set_used(used)

        for row in self.rows:
            row.clear_results()
            row.remove_button.setEnabled(len(self.rows) > MIN_HANDS)

        self.add_button.setEnabled(len(self.rows) < MAX_TABLE_SEATS)
        self._update_buttons()

    def _read_input(self) -> tuple[list[PlayerHand], list[Card]]:
        """Every player's hand or range, and the board; raises ValueError."""
        hands: list[PlayerHand] = []

        for index, row in enumerate(self.rows, start=1):
            if row.is_range:
                if not row.range.labels:
                    raise ValueError(f"Player {index}: the range is empty.")

                hands.append(row.range)
            elif len(row.cards) == 1:
                raise ValueError(
                    f"Player {index}: choose two cards, or none for a random hand."
                )
            else:
                hands.append(tuple(row.cards) or None)

        board = [slot.card for slot in self.board_slots if slot.card is not None]

        return hands, board

    # --- Calculation -----------------------------------------------------------

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
        self._uses_ranges = any(not isinstance(hand, tuple) for hand in hands)
        self._target = calculator.total_boards or MONTE_CARLO_BOARDS
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

        try:
            calculator.run(min(self._chunk, self._target - calculator.boards))
        except RuntimeError as error:
            self.error_label.setText(str(error))
            self.stop()
            return

        self._show_result(calculator.result())

        if calculator.boards >= self._target or calculator.finished:
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

        deals = "deals" if self._uses_ranges else "boards"
        counted = f"{result.boards:,}".replace(",", " ")

        if result.exact:
            total = f"{self._target:,}".replace(",", " ")
            self.status_label.setText(f"Exact: {counted} of {total} {deals} counted")
        else:
            self.status_label.setText(
                f"Estimate: {counted} random {deals} (Monte Carlo, 95% margins)"
            )

    def _update_buttons(self) -> None:
        running = self._timer.isActive()
        self.stop_button.setEnabled(running)
        self.calculate_button.setEnabled(not running)

    def _on_back_clicked(self) -> None:
        self.stop()
        self.back_requested.emit()
