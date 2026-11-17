"""The hand replayer (V1.1): a saved hand, step by step, on the table.

The hand is dealt again through the engine (``backend.application.replay``),
so the table shows exactly what it showed while the hand was played: your
cards, the bets, the pot, the cards turned face up after an all-in with each
player's chance of winning, and the showdown. "Show all cards" also shows
the cards nobody saw. Hands saved before V1.1 cannot be replayed (their
cards were not recorded): their history is shown as text.
"""

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.application.game_modes import MODE_LABELS
from backend.application.hand_records import HandRecord, SessionRecord
from backend.application.replay import HandReplay, ReplayError
from backend.poker_engine.models import ActionEvent, Hand
from frontend.components.table_widget import TableWidget
from frontend.formatting import describe_action, describe_result, format_cards
from frontend.pacing import DEFAULT_TABLE_SPEED, TABLE_SPEEDS, table_speed
from frontend.runout import RunoutEquity

from .game_screen import build_table_state


def action_line(event: ActionEvent, timed_out: tuple[int, ...]) -> str:
    line = f"{event.player}: {describe_action(event)}"

    return f"{line} (ran out of time)" if event.sequence in timed_out else line


def hand_header(session: SessionRecord, record: HandRecord) -> list[str]:
    lines = [f"── Hand #{record.number} — blinds {record.blind_level.describe()} ──"]
    cards = record.hole_cards(session.human)

    if cards:
        lines.append(f"Dealt to {session.human}: {format_cards(cards)}")

    return lines


def record_history(session: SessionRecord, record: HandRecord) -> list[str]:
    """The text history of a hand from its record alone (no replay needed)."""
    lines = hand_header(session, record)
    streets = iter(record.streets[1:])
    street = record.streets[0].street if record.streets else None

    for event in record.actions:
        while event.street != street:
            dealt = next(streets)
            street = dealt.street
            lines.append(f"*** {street} *** {format_cards(dealt.community_cards)}")

        lines.append(action_line(event, record.timed_out_actions))

        if event.sequence == record.revealed_after_action:
            lines.append("*** Cards revealed ***")

    for dealt in streets:
        lines.append(f"*** {dealt.street} *** {format_cards(dealt.community_cards)}")

    for name, evaluation in record.showdown.items():
        lines.append(f"{name} shows {evaluation.name}")

    lines += [f"{name} wins {amount}" for name, amount in record.payouts.items()]

    return lines


class ReplayerScreen(QWidget):
    """Replays the hands of a saved session."""

    back_requested = Signal()
    show_in_big_blinds_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session: SessionRecord | None = None
        self.hand_index = 0
        self.replay: HandReplay | None = None
        self.hand: Hand | None = None
        self.step = 0
        self._step_lines: list[list[str]] = []
        """The history lines each step adds (step 0: the deal)."""
        self._equity = RunoutEquity()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)

        self.info_label = QLabel()
        self.info_label.setObjectName("sectionTitle")
        self.first_button = QPushButton("|◀")
        self.first_button.setToolTip("Back to the deal (Home)")
        self.first_button.setShortcut(QKeySequence("Home"))
        self.previous_button = QPushButton("◀")
        self.previous_button.setToolTip("Previous step (Left)")
        self.previous_button.setShortcut(QKeySequence("Left"))
        self.play_button = QPushButton("Play")
        self.play_button.setShortcut(QKeySequence("Space"))
        self.next_button = QPushButton("▶")
        self.next_button.setToolTip("Next step (Right)")
        self.next_button.setShortcut(QKeySequence("Right"))
        self.last_button = QPushButton("▶|")
        self.last_button.setToolTip("End of the hand (End)")
        self.last_button.setShortcut(QKeySequence("End"))
        self.step_label = QLabel()
        self.previous_hand_button = QPushButton("◀ Hand")
        self.previous_hand_button.setShortcut(QKeySequence("PgUp"))
        self.next_hand_button = QPushButton("Hand ▶")
        self.next_hand_button.setShortcut(QKeySequence("PgDown"))
        self.speed_combo = QComboBox()

        for speed in TABLE_SPEEDS:
            self.speed_combo.addItem(speed.name, speed.name)

        self.speed_combo.setCurrentIndex(self.speed_combo.findData(DEFAULT_TABLE_SPEED))
        self.show_all_check = QCheckBox("Show all cards")
        self.show_all_check.setToolTip("Also show the cards nobody saw.")
        self.show_all_check.toggled.connect(self._render)
        self.big_blinds_check = QCheckBox("Show in BB")
        self.big_blinds_check.toggled.connect(self._on_big_blinds_toggled)
        self.back_button = QPushButton("Back")

        self.first_button.clicked.connect(lambda: self.go_to(0))
        self.previous_button.clicked.connect(lambda: self.go_to(self.step - 1))
        self.play_button.clicked.connect(self.toggle_play)
        self.next_button.clicked.connect(lambda: self.go_to(self.step + 1))
        self.last_button.clicked.connect(self._go_to_end)
        self.previous_hand_button.clicked.connect(lambda: self._show_other_hand(-1))
        self.next_hand_button.clicked.connect(lambda: self._show_other_hand(1))
        self.back_button.clicked.connect(self._on_back_clicked)

        for button in (
            self.first_button,
            self.previous_button,
            self.play_button,
            self.next_button,
            self.last_button,
            self.previous_hand_button,
            self.next_hand_button,
            self.back_button,
        ):
            button.setObjectName("small")

        self.table_widget = TableWidget()
        self.message_label = QLabel()
        self.message_label.setObjectName("statusText")
        self.message_label.setWordWrap(True)
        self.message_label.setContentsMargins(40, 40, 40, 40)
        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self.table_widget)
        self.view_stack.addWidget(self.message_label)

        self.history_view = QPlainTextEdit()
        self.history_view.setReadOnly(True)
        self.history_view.setFixedWidth(290)

        top = QHBoxLayout()
        top.addWidget(self.info_label, stretch=1)
        top.addWidget(self.show_all_check)
        top.addWidget(self.big_blinds_check)
        top.addWidget(self.back_button)

        controls = QHBoxLayout()
        controls.addWidget(self.previous_hand_button)
        controls.addStretch()

        for widget in (
            self.first_button,
            self.previous_button,
            self.play_button,
            self.next_button,
            self.last_button,
        ):
            controls.addWidget(widget)

        controls.addWidget(self.step_label)
        controls.addStretch()
        controls.addWidget(QLabel("Speed"))
        controls.addWidget(self.speed_combo)
        controls.addWidget(self.next_hand_button)

        left = QVBoxLayout()
        left.addLayout(top)
        left.addWidget(self.view_stack, stretch=1)
        left.addLayout(controls)

        history_title = QLabel("HAND HISTORY")
        history_title.setObjectName("sectionTitle")
        right = QVBoxLayout()
        right.addWidget(history_title)
        right.addWidget(self.history_view, stretch=1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(14)
        layout.addLayout(left, stretch=1)
        layout.addLayout(right)

    # --- Hands ---------------------------------------------------------------

    @property
    def record(self) -> HandRecord | None:
        if self.session is None or not self.session.hands:
            return None

        return self.session.hands[self.hand_index]

    @property
    def is_playing(self) -> bool:
        return self.play_button.text() == "Pause"

    def show_hand(self, session: SessionRecord, index: int) -> None:
        """Show hand ``index`` of ``session``, at the deal."""
        self.stop()
        self.session = session
        self.hand_index = max(0, min(index, len(session.hands) - 1))
        record = self.record
        self.replay = None
        self.hand = None
        self._step_lines = []

        if record is None:
            self._show_message("This session has no hands.", [])
            return

        mode = MODE_LABELS[session.mode].upper()
        self.info_label.setText(
            f"HAND #{record.number} ({self.hand_index + 1} OF {len(session.hands)})"
            f"   ·   {mode} {record.blind_level.describe()}"
            f"   ·   {session.started:%d %b %Y %H:%M}"
        )

        try:
            self.replay = HandReplay(record)
        except ReplayError as error:
            self._show_message(str(error), record_history(session, record))
            return

        self._step_lines = self._history_by_step(session, self.replay)
        self.view_stack.setCurrentWidget(self.table_widget)
        self.go_to(0)

    def _show_message(self, text: str, history: list[str]) -> None:
        self.message_label.setText(text)
        self.view_stack.setCurrentWidget(self.message_label)
        self.history_view.setPlainText("\n".join(history))
        self.step_label.setText("")
        self._update_buttons()

    def _show_other_hand(self, offset: int) -> None:
        if self.session is not None:
            self.show_hand(self.session, self.hand_index + offset)

    def _history_by_step(
        self, session: SessionRecord, replay: HandReplay
    ) -> list[list[str]]:
        record = replay.record
        hand = replay.start()
        steps = [
            hand_header(session, record)
            + [action_line(event, ()) for event in hand.actions]
        ]

        while not hand.finished:
            streets = len(hand.streets)
            event = replay.advance(hand)
            lines = []

            if event is not None:
                lines.append(action_line(event, record.timed_out_actions))

            if event is not None and event.sequence == hand.revealed_after_action:
                lines.append("*** Cards revealed ***")

            for street in hand.streets[streets:]:
                lines.append(
                    f"*** {street.street} *** {format_cards(street.community_cards)}"
                )

            if hand.finished:
                lines += self._result_lines(hand)

            steps.append(lines)

        return steps

    @staticmethod
    def _result_lines(hand: Hand) -> list[str]:
        lines = []

        for player in hand.table.players:
            evaluation = hand.showdown_evaluations.get(player.name)

            if evaluation is not None:
                cards = format_cards(player.hand)
                lines.append(f"{player.name} shows {cards} ({evaluation.name})")

        return lines + describe_result(hand)

    # --- Steps ---------------------------------------------------------------

    def go_to(self, step: int) -> None:
        """Show the hand after ``step`` steps (kept within the hand)."""
        replay = self.replay

        if replay is None:
            return

        self.step = max(0, min(step, replay.step_count))
        self.hand = replay.hand_at(self.step)
        lines = [line for lines in self._step_lines[: self.step + 1] for line in lines]
        self.history_view.setPlainText("\n".join(lines))
        self.history_view.verticalScrollBar().setValue(
            self.history_view.verticalScrollBar().maximum()
        )
        self.step_label.setText(f"Step {self.step} / {replay.step_count}")
        self._render()
        self._update_buttons()

    def _go_to_end(self) -> None:
        if self.replay is not None:
            self.go_to(self.replay.step_count)

    @property
    def at_end(self) -> bool:
        return self.replay is None or self.step >= self.replay.step_count

    def toggle_play(self) -> None:
        if self.is_playing:
            self.stop()
            return

        if self.replay is None:
            return

        if self.at_end:
            self.go_to(0)

        self.play_button.setText("Pause")
        self._schedule()

    def stop(self) -> None:
        self._timer.stop()
        self.play_button.setText("Play")

    def _schedule(self) -> None:
        speed = table_speed(self.speed_combo.currentData())
        self._timer.start(speed.action_delay_ms)

    def _on_timer(self) -> None:
        self.go_to(self.step + 1)

        if self.at_end:
            self.stop()
        else:
            self._schedule()

    def _update_buttons(self) -> None:
        replayable = self.replay is not None
        hands = len(self.session.hands) if self.session is not None else 0

        self.first_button.setEnabled(replayable and self.step > 0)
        self.previous_button.setEnabled(replayable and self.step > 0)
        self.next_button.setEnabled(replayable and not self.at_end)
        self.last_button.setEnabled(replayable and not self.at_end)
        self.play_button.setEnabled(replayable)
        self.previous_hand_button.setEnabled(self.hand_index > 0)
        self.next_hand_button.setEnabled(self.hand_index < hands - 1)

    def _on_back_clicked(self) -> None:
        self.stop()
        self.back_requested.emit()

    # --- Display -------------------------------------------------------------

    @property
    def show_in_big_blinds(self) -> bool:
        return self.big_blinds_check.isChecked()

    def set_show_in_big_blinds(self, enabled: bool) -> None:
        self.big_blinds_check.blockSignals(True)
        self.big_blinds_check.setChecked(enabled)
        self.big_blinds_check.blockSignals(False)
        self._render()

    def _on_big_blinds_toggled(self, enabled: bool) -> None:
        self._render()
        self.show_in_big_blinds_changed.emit(enabled)

    def _render(self) -> None:
        if self.hand is None or self.session is None:
            return

        self.table_widget.set_state(
            build_table_state(
                self.hand,
                human_name=self.session.human,
                show_all_cards=self.show_all_check.isChecked(),
                in_big_blinds=self.show_in_big_blinds,
                equities=self._equity.texts(self.hand),
            )
        )
