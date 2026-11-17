"""Watch mode of the Bot Arena: the simulated hands played on the table.

The hands come from the same batches, in the same order, as a fast run of the
configuration, so a fast result can be inspected hand by hand.
"""

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from backend.poker_engine.models import Hand
from backend.simulation.config import SimulationConfig
from backend.simulation.result import SimulationTotals
from backend.simulation.runner import Batch, BatchSchedule, plan_batches
from frontend import theme
from frontend.components.table_widget import TableWidget
from frontend.formatting import describe_action, describe_result, format_cards
from frontend.runout import RunoutEquity, is_running_out, runout_delay_ms

from .game_screen import build_table_state

SPEEDS_MS = {"Slow": 1200, "Normal": 600, "Fast": 150}
HAND_END_PAUSE_FACTOR = 3


class ArenaWatchScreen(QWidget):
    """Plays a Bot Arena configuration hand by hand on the table."""

    back_requested = Signal()
    show_in_big_blinds_changed = Signal(bool)
    """Emitted when the user switches between chips and big blinds."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config: SimulationConfig | None = None
        self.schedule: BatchSchedule | None = None
        self.hand: Hand | None = None
        self.hands_played = 0
        self._pending_batches: list[Batch] = []
        self._finished_totals: SimulationTotals | None = None
        self._logged_streets = 0
        self._reveal_logged = False
        self._runout_equity = RunoutEquity()
        self._done = False

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)

        self.info_label = QLabel()
        self.info_label.setObjectName("sectionTitle")
        self.standings_label = QLabel()
        self.standings_label.setWordWrap(True)

        self.speed_combo = QComboBox()

        for name, delay in SPEEDS_MS.items():
            self.speed_combo.addItem(name, delay)

        self.speed_combo.setCurrentIndex(1)
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.toggle_pause)
        self.step_button = QPushButton("Step")
        self.step_button.setToolTip("Play one action (while paused).")
        self.step_button.clicked.connect(self.step)
        self.spectator_check = QCheckBox("Show all cards")
        self.spectator_check.setChecked(True)
        self.spectator_check.toggled.connect(self._render)
        self.big_blinds_check = QCheckBox("Show in BB")
        self.big_blinds_check.setToolTip("Show stacks, bets and the pot in big blinds.")
        self.big_blinds_check.toggled.connect(self._on_big_blinds_toggled)
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self._on_back_clicked)

        for button in (self.pause_button, self.step_button, self.back_button):
            button.setObjectName("small")

        self.table_widget = TableWidget()
        self.history_view = QPlainTextEdit()
        self.history_view.setReadOnly(True)
        self.history_view.setFixedWidth(290)
        self.history_view.setMaximumBlockCount(3000)

        controls = QHBoxLayout()
        controls.addSpacing(theme.SETTINGS_BUTTON_ROOM)
        controls.addWidget(self.info_label, stretch=1)
        controls.addWidget(QLabel("Speed"))
        controls.addWidget(self.speed_combo)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.step_button)
        controls.addWidget(self.spectator_check)
        controls.addWidget(self.big_blinds_check)
        controls.addWidget(self.back_button)

        left = QVBoxLayout()
        left.addLayout(controls)
        left.addWidget(self.table_widget, stretch=1)
        left.addWidget(self.standings_label)

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

    # --- Control -------------------------------------------------------------

    @property
    def is_paused(self) -> bool:
        return self.pause_button.text() == "Resume"

    @property
    def is_complete(self) -> bool:
        """True once every hand was played, or the run stopped on an error."""
        return self._done

    @property
    def show_in_big_blinds(self) -> bool:
        return self.big_blinds_check.isChecked()

    def set_show_in_big_blinds(self, enabled: bool) -> None:
        """Show amounts in big blinds or chips, without emitting the change."""
        self.big_blinds_check.blockSignals(True)
        self.big_blinds_check.setChecked(enabled)
        self.big_blinds_check.blockSignals(False)
        self._render()

    def _on_big_blinds_toggled(self, enabled: bool) -> None:
        self._render()
        self.show_in_big_blinds_changed.emit(enabled)

    def start(self, config: SimulationConfig) -> None:
        """Start watching a configuration from its first hand."""
        self.stop()
        self.config = config.with_seed()
        self._pending_batches = plan_batches(self.config)
        self._finished_totals = SimulationTotals.empty(self.config)
        self.schedule = None
        self.hand = None
        self.hands_played = 0
        self._done = False
        self.history_view.clear()
        self.pause_button.setText("Pause")
        self.pause_button.setEnabled(True)
        self.step_button.setEnabled(False)
        self._log(f"Seed {self.config.seed} — {', '.join(self.config.seat_names)}")
        self.step()
        self._schedule_next()

    def stop(self) -> None:
        self._timer.stop()

    def toggle_pause(self) -> None:
        if self.pause_button.text() == "Pause":
            self._timer.stop()
            self.pause_button.setText("Resume")
            self.step_button.setEnabled(True)
        else:
            self.pause_button.setText("Pause")
            self.step_button.setEnabled(False)
            self._schedule_next()

    def step(self) -> None:
        """Play one action, deal one street, or start the next hand."""
        if self.config is None or self._done:
            return

        if self.hand is None or self.hand.finished:
            self._start_next_hand()
        else:
            schedule = self._require_schedule()
            event = schedule.require_table().step()

            if event is not None:
                self._log(f"{event.player}: {describe_action(event)}")

            self._log_reveal()
            self._log_streets()

            if self.hand.finished:
                self._finish_hand()

        self._render()

    def _on_timer(self) -> None:
        self.step()
        self._schedule_next()

    def _schedule_next(self) -> None:
        if self.is_paused or self._done:
            return

        delay = self.speed_combo.currentData()

        if self.hand is not None and self.hand.finished:
            delay *= HAND_END_PAUSE_FACTOR
        elif (
            self.hand is not None
            and is_running_out(self.hand)
            and self.hand.current_player is None
        ):
            delay = runout_delay_ms(delay)

        self._timer.start(delay)

    def _on_back_clicked(self) -> None:
        self.stop()
        self.back_requested.emit()

    # --- Hands ---------------------------------------------------------------

    def _require_schedule(self) -> BatchSchedule:
        if self.schedule is None:
            raise RuntimeError("No batch is being played.")

        return self.schedule

    def _start_next_hand(self) -> None:
        assert self.config is not None

        while True:
            if self.schedule is None:
                if not self._pending_batches:
                    self._on_complete()
                    return

                self.schedule = BatchSchedule(self.config, self._pending_batches.pop(0))

            hand = self.schedule.start_next_hand()

            if hand is not None:
                break

            assert self._finished_totals is not None
            self._finished_totals.merge(self.schedule.totals)
            self.schedule = None

        self.hand = hand
        self.hands_played += 1
        self._logged_streets = 0
        self._reveal_logged = False
        config = self.config
        self.info_label.setText(
            f"HAND #{self.hands_played}   ·   BLINDS {config.small_blind}/"
            f"{config.big_blind}   ·   SEED {config.seed}"
        )
        self._log(f"\n── Hand #{self.hands_played} ──")

        for event in hand.actions:
            self._log(f"{event.player}: {describe_action(event)}")

        for player in hand.table.players:
            if player.hand:
                self._log(f"{player.name}: {format_cards(player.hand)}")

    def _finish_hand(self) -> None:
        hand = self.hand
        assert hand is not None

        for name, evaluation in hand.showdown_evaluations.items():
            cards = next(p.hand for p in hand.table.players if p.name == name)
            self._log(f"{name} shows {format_cards(cards)} ({evaluation.name})")

        for line in describe_result(hand):
            self._log(line)

        try:
            self._require_schedule().finish_hand()
        except Exception as error:  # noqa: BLE001 - shown to the user
            self._log(f"\n{type(error).__name__}: {error}")
            self.stop()
            self._done = True
            self.pause_button.setEnabled(False)
            self.step_button.setEnabled(False)

        self._update_standings()

    def _on_complete(self) -> None:
        self._done = True
        self._log("\nAll hands have been played.")
        self.info_label.setText(f"COMPLETE   ·   {self.hands_played} HANDS")
        self.pause_button.setEnabled(False)
        self.step_button.setEnabled(False)

    def _update_standings(self) -> None:
        if self.config is None or self._finished_totals is None:
            return

        totals = SimulationTotals.empty(self.config)
        totals.merge(self._finished_totals)

        if self.schedule is not None:
            totals.merge(self.schedule.totals)

        ranked = sorted(totals.players.values(), key=lambda s: -s.net_chips)
        self.standings_label.setText(
            "Net chips:   "
            + "   ·   ".join(
                f"{stats.name} {stats.net_chips:+,}".replace(",", " ")
                for stats in ranked
            )
        )

    def _log_reveal(self) -> None:
        """Mark the moment the cards are turned face up (an all-in called)."""
        hand = self.hand
        assert hand is not None

        if not self._reveal_logged and hand.revealed_after_action is not None:
            self._reveal_logged = True
            self._log("*** Cards revealed ***")

    def _log_streets(self) -> None:
        hand = self.hand
        assert hand is not None

        for street in hand.streets[self._logged_streets :]:
            if street.community_cards:
                self._log(
                    f"*** {street.street} *** {format_cards(street.community_cards)}"
                )

        self._logged_streets = len(hand.streets)

    def _render(self) -> None:
        if self.hand is not None:
            self.table_widget.set_state(
                build_table_state(
                    self.hand,
                    human_name=None,
                    show_all_cards=self.spectator_check.isChecked(),
                    in_big_blinds=self.show_in_big_blinds,
                    equities=self._runout_equity.texts(self.hand),
                )
            )

    def _log(self, text: str) -> None:
        self.history_view.appendPlainText(text)
