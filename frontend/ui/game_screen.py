"""The game screen: table, action panel and hand history.

The screen never runs a blocking game loop. Each bot action or street is one
short step triggered by a timer, and the human acts through the action panel.
"""

import math
import time
from collections.abc import Collection, Mapping
from typing import Protocol

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.application.action_clock import (
    WARNING_SECONDS,
    ActionClock,
    ClockPreset,
    TimeSource,
    record_timeout,
    timeout_action,
)
from backend.application.bankroll import GameAccount, TransactionType
from backend.application.controllers import HumanController, PlayerController
from backend.poker_engine.actions import Action
from backend.poker_engine.betting import IllegalActionError, get_legal_actions
from backend.poker_engine.models import ActionEvent, Hand, Player
from backend.poker_engine.session import GameSession
from frontend.components.action_panel import ActionPanel
from frontend.components.seat_widget import SeatHighlight, SeatState
from frontend.components.table_widget import TableState, TableWidget
from frontend.formatting import (
    describe_action,
    describe_result,
    format_amount,
    format_cards,
)
from frontend.pacing import DEFAULT_TABLE_SPEED, TABLE_SPEEDS, table_speed
from frontend.runout import (
    RunoutEquity,
    is_running_out,
    revealed_names,
    runout_delay_ms,
)

CLOCK_TICK_MS = 100
CLOCK_BAR_STEPS = 1000
CLOCK_COLORS = {"normal": "#3ddc84", "warning": "#f2a33a", "bank": "#5aa9f2"}


class TableGame(Protocol):
    """A game played step by step at one table: ``PokerGame`` or ``Tournament``."""

    session: GameSession
    hand: Hand | None

    @property
    def controllers(self) -> Mapping[str, PlayerController]: ...

    @property
    def is_hand_in_progress(self) -> bool: ...

    @property
    def is_waiting_for_human(self) -> bool: ...

    def start_hand(self) -> Hand: ...

    def step(self) -> ActionEvent | None: ...


def hand_big_blind(hand: Hand) -> int:
    """The big blind a hand is played with (the level's, in a tournament)."""
    if hand.blind_level is not None:
        return hand.blind_level.big_blind

    return hand.min_bet


def player_status(player: Player, hand: Hand, big_blind: int | None = None) -> str:
    """Return the short status line shown under a player's stack.

    Amounts are in big blinds of ``big_blind`` when it is set.
    """
    if player.is_eliminated:
        return "Out"

    if hand.finished and player.name in hand.payouts:
        return f"Wins {format_amount(hand.payouts[player.name], big_blind)}"

    if player.folded:
        return "Folded"

    if player.all_in:
        return "All-in"

    return player.position or ""


def build_table_state(
    hand: Hand,
    human_name: str | None,
    show_all_cards: bool = False,
    in_big_blinds: bool = False,
    equities: Mapping[str, str] | None = None,
    hidden: Collection[str] = (),
) -> TableState:
    """Translate the engine state into what the table displays.

    Seats are rotated so the human sits at the bottom; a spectator (no human)
    sees the first seat at the bottom. Other players' cards stay face down
    unless they reached the showdown or the betting is over (an all-in
    called), or ``show_all_cards`` is set. With ``in_big_blinds``, amounts
    are shown in big blinds of the hand. ``equities`` adds each player's
    chance of winning to their status during the run-out. The cards of the
    ``hidden`` players (nobody saw them) always stay face down.
    """
    big_blind = hand_big_blind(hand) if in_big_blinds else None
    revealed = revealed_names(hand)
    equities = equities or {}
    players = hand.table.players
    human_index = next((i for i, p in enumerate(players) if p.name == human_name), 0)
    ordered = players[human_index:] + players[:human_index]

    seats = []

    for player in ordered:
        if hand.finished and player.name in hand.payouts:
            highlight = SeatHighlight.WINNER
        elif player is hand.current_player:
            highlight = SeatHighlight.ACTING
        else:
            highlight = SeatHighlight.NONE

        shows_cards = player.name not in hidden and (
            show_all_cards
            or player.name == human_name
            or player.name in hand.showdown_evaluations
            or player.name in revealed
        )
        status = player_status(player, hand, big_blind)

        if player.name in equities:
            equity = equities[player.name]
            status = f"{status} · {equity}" if status else equity

        seats.append(
            SeatState(
                name=player.name,
                stack=player.stack,
                cards=tuple(player.hand),
                cards_face_up=shows_cards,
                status=status,
                highlight=highlight,
                dimmed=player.folded,
                big_blind=big_blind,
            )
        )

    return TableState(
        seats=tuple(seats),
        bets=tuple(player.current_bet for player in ordered),
        dealer_seat=ordered.index(hand.table.dealer),
        community_cards=tuple(hand.community_cards),
        pot=hand.pot,
        big_blind=big_blind,
    )


class GameScreen(QWidget):
    """Plays a game and displays its state."""

    menu_requested = Signal()
    show_in_big_blinds_changed = Signal(bool)
    """Emitted when the user switches between chips and big blinds."""
    speed_changed = Signal(str)
    """Emitted with the speed the user picked (see ``frontend.pacing``)."""
    auto_next_hand_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        speed = table_speed(DEFAULT_TABLE_SPEED)
        self.step_delay_ms = speed.action_delay_ms
        """Before each bot action or street."""
        self.hand_pause_ms = speed.hand_pause_ms
        """The result shown before the next hand starts on its own."""
        self._next_hand_due = False
        """A hand is over and the next one may start on its own."""
        self._game: TableGame | None = None
        self._human_name = ""
        self._logged_street_count = 0
        self._reveal_logged = False
        self._runout_equity = RunoutEquity()
        self.action_clock: ActionClock | None = None
        self.clock_time_source: TimeSource = time.monotonic
        """Where the action clock reads the time (a fake one in tests)."""
        self._clock_counted_hand: Hand | None = None
        self.paused = False
        self.account: GameAccount | None = None
        """The cash game's money in the bankroll (None: not paid for)."""

        self._step_timer = QTimer(self)
        self._step_timer.setSingleShot(True)
        self._step_timer.timeout.connect(self._play_step)
        self._action_clock_timer = QTimer(self)
        """Refreshes the action clock's bar and detects a time out."""
        self._action_clock_timer.setInterval(CLOCK_TICK_MS)
        self._action_clock_timer.timeout.connect(self._on_clock_tick)
        self._next_hand_timer = QTimer(self)
        self._next_hand_timer.setSingleShot(True)
        self._next_hand_timer.timeout.connect(self._on_next_hand_timer)

        self.pause_button = QPushButton("Pause")
        self.pause_button.setObjectName("small")
        self.pause_button.setToolTip("Freezes the clocks and the table.")
        self.pause_button.clicked.connect(self.toggle_pause)

        self.speed_combo = QComboBox()
        self.speed_combo.setToolTip("How fast the bots act and the next hand comes.")

        for table_speed_choice in TABLE_SPEEDS:
            self.speed_combo.addItem(table_speed_choice.name, table_speed_choice.name)

        self.speed_combo.setCurrentIndex(self.speed_combo.findData(speed.name))
        self.speed_combo.activated.connect(self._on_speed_chosen)
        self.auto_next_check = QCheckBox("Auto next hand")
        self.auto_next_check.setToolTip("Deal the next hand on its own.")
        self.auto_next_check.setChecked(True)
        self.auto_next_check.toggled.connect(self._on_auto_next_toggled)

        self.clock_bar = QProgressBar()
        self.clock_bar.setRange(0, CLOCK_BAR_STEPS)
        self.clock_bar.setFixedHeight(16)
        self.clock_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_bar.hide()

        self.info_label = QLabel()
        self.info_label.setObjectName("sectionTitle")
        self.menu_button = QPushButton("Menu")
        self.menu_button.setObjectName("small")
        self.menu_button.clicked.connect(self._on_menu_clicked)
        self.big_blinds_check = QCheckBox("Show in BB")
        self.big_blinds_check.setToolTip("Show stacks, bets and the pot in big blinds.")
        self.big_blinds_check.toggled.connect(self._on_big_blinds_toggled)

        self.table_widget = TableWidget()
        self.action_panel = ActionPanel()
        self.action_panel.action_chosen.connect(self._on_action_chosen)

        self.result_label = QLabel()
        self.result_label.setObjectName("resultText")
        self.result_label.setWordWrap(True)
        self.next_hand_button = QPushButton("Next hand")
        self.next_hand_button.setObjectName("primary")
        self.next_hand_button.clicked.connect(self._start_next_hand)
        self.rebuy_button = QPushButton("Rebuy")
        self.rebuy_button.setObjectName("accent")
        self.rebuy_button.clicked.connect(self._on_rebuy_clicked)

        self.history_view = QPlainTextEdit()
        self.history_view.setReadOnly(True)
        self.history_view.setFixedWidth(270)
        self.history_view.setMaximumBlockCount(2000)

        self.bottom_stack = QStackedWidget()
        self.bottom_stack.addWidget(self.action_panel)
        self.bottom_stack.addWidget(self._build_result_page())
        self.bottom_stack.setFixedHeight(84)

        self._build_layout()

    def _build_result_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.result_label, stretch=1)
        layout.addWidget(self.rebuy_button)
        layout.addWidget(self.next_hand_button)

        for button in (self.rebuy_button, self.next_hand_button):
            button.setMinimumHeight(48)
            button.setMinimumWidth(150)

        return page

    def _build_layout(self) -> None:
        top_bar = QHBoxLayout()
        top_bar.addWidget(self.info_label, stretch=1)
        top_bar.addWidget(QLabel("Speed"))
        top_bar.addWidget(self.speed_combo)
        top_bar.addWidget(self.auto_next_check)
        top_bar.addWidget(self.big_blinds_check)
        top_bar.addWidget(self.pause_button)
        top_bar.addWidget(self.menu_button)

        bottom_panel = QFrame()
        bottom_panel.setObjectName("panel")
        bottom_layout = QVBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(16, 12, 16, 12)
        bottom_layout.addWidget(self.clock_bar)
        bottom_layout.addWidget(self.bottom_stack)

        left_layout = QVBoxLayout()
        self.left_layout = left_layout
        """Top bar, table and bottom panel; subclasses insert above the table."""
        left_layout.addLayout(top_bar)
        left_layout.addWidget(self.table_widget, stretch=1)
        left_layout.addWidget(bottom_panel)

        history_title = QLabel("HAND HISTORY")
        history_title.setObjectName("sectionTitle")
        right_layout = QVBoxLayout()
        right_layout.addWidget(history_title)
        right_layout.addWidget(self.history_view, stretch=1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(14)
        layout.addLayout(left_layout, stretch=1)
        layout.addLayout(right_layout)

    # ------------------------------------------------------------------
    # Game flow
    # ------------------------------------------------------------------

    @property
    def game(self) -> TableGame | None:
        return self._game

    @property
    def show_in_big_blinds(self) -> bool:
        return self.big_blinds_check.isChecked()

    def set_show_in_big_blinds(self, enabled: bool) -> None:
        """Show amounts in big blinds or chips, without emitting the change."""
        self.big_blinds_check.blockSignals(True)
        self.big_blinds_check.setChecked(enabled)
        self.big_blinds_check.blockSignals(False)
        self._refresh_amounts()

    def _on_big_blinds_toggled(self, enabled: bool) -> None:
        self._refresh_amounts()
        self.show_in_big_blinds_changed.emit(enabled)

    def _refresh_amounts(self) -> None:
        """Redraw the table and the action panel in the current unit."""
        hand = self._game.hand if self._game is not None else None

        if hand is None:
            self.action_panel.set_big_blind(None)
            return

        self._render_table(hand)
        self.action_panel.set_big_blind(
            hand_big_blind(hand) if self.show_in_big_blinds else None
        )

    # --- Speed and next hand ------------------------------------------------------

    @property
    def speed(self) -> str:
        return self.speed_combo.currentData()

    def set_speed(self, name: str) -> None:
        """Use a table speed, without emitting the change."""
        speed = table_speed(name)
        self.speed_combo.setCurrentIndex(self.speed_combo.findData(speed.name))
        self.step_delay_ms = speed.action_delay_ms
        self.hand_pause_ms = speed.hand_pause_ms

    def _on_speed_chosen(self, index: int) -> None:
        name = self.speed_combo.itemData(index)
        self.set_speed(name)
        self.speed_changed.emit(name)

    @property
    def auto_next_hand(self) -> bool:
        return self.auto_next_check.isChecked()

    def set_auto_next_hand(self, enabled: bool) -> None:
        """Deal the next hand on its own or not, without emitting the change."""
        self.auto_next_check.blockSignals(True)
        self.auto_next_check.setChecked(enabled)
        self.auto_next_check.blockSignals(False)
        self._restart_next_hand_timer()

    def _on_auto_next_toggled(self, enabled: bool) -> None:
        self._restart_next_hand_timer()
        self.auto_next_hand_changed.emit(enabled)

    def _schedule_next_hand(self) -> None:
        """The next hand may start on its own, after the result is shown."""
        self._next_hand_due = True
        self._restart_next_hand_timer()

    def _cancel_next_hand(self) -> None:
        self._next_hand_due = False
        self._next_hand_timer.stop()

    def _restart_next_hand_timer(self) -> None:
        if self._next_hand_due and self.auto_next_hand and not self.paused:
            self._next_hand_timer.start(self.hand_pause_ms)
        else:
            self._next_hand_timer.stop()

    def _on_next_hand_timer(self) -> None:
        if self._game is None or self.paused or not self._next_hand_due:
            return

        self._next_hand_due = False
        self._start_next_hand()

    def _render_table(self, hand: Hand) -> None:
        self.table_widget.set_state(
            build_table_state(
                hand,
                self._human_name,
                in_big_blinds=self.show_in_big_blinds,
                equities=self._runout_equity.texts(hand),
            )
        )

    def start_game(
        self,
        game: TableGame,
        human_name: str,
        clock: ClockPreset | None = None,
        account: GameAccount | None = None,
    ) -> None:
        """Start playing a new game with the given human player.

        ``clock`` gives the human a time to act and a time bank (None: no
        clock). ``account`` is the cash game's money in the bankroll: its
        stack behind is kept up to date and cashed out when the game stops.
        """
        if not isinstance(game.controllers.get(human_name), HumanController):
            raise ValueError(f"{human_name} is not controlled by a human.")

        self._step_timer.stop()
        self._game = game
        self._human_name = human_name
        self.account = account
        self._set_clock(clock)
        self.history_view.clear()
        self._start_next_hand()

    def stop(self) -> None:
        """Stop the game in progress, if any; a cash game is cashed out."""
        self._step_timer.stop()
        self._cancel_next_hand()
        self._stop_clock_display()

        if self.account is not None and self._game is not None:
            # Chips already in the pot stay there, as with a fold.
            self.account.cash_out(self._human_player().stack)

        self.account = None
        self._game = None

    def _set_clock(self, preset: ClockPreset | None) -> None:
        """Give the human a fresh action clock (or none), and reset Pause."""
        self.action_clock = (
            ActionClock(preset, self.clock_time_source) if preset is not None else None
        )
        self._clock_counted_hand = None
        self.paused = False
        self.pause_button.setText("Pause")

    # --- Pause ------------------------------------------------------------------

    def toggle_pause(self) -> None:
        """Freeze (or restart) the clocks and the table."""
        if self._game is None:
            return

        self.paused = not self.paused
        self.pause_button.setText("Resume" if self.paused else "Pause")
        self._on_pause_changed()

    def _on_pause_changed(self) -> None:
        clock = self.action_clock
        game = self._require_game()

        self._restart_next_hand_timer()

        if self.paused:
            self._step_timer.stop()
            self._action_clock_timer.stop()

            if clock is not None:
                clock.pause()

            if game.is_waiting_for_human:
                self.action_panel.set_legal_actions(
                    (), pot=0, current_bet=0, player_bet=0
                )
            return

        if clock is not None:
            clock.resume()

        if game.is_hand_in_progress:
            self._after_step()

    # --- Action clock -----------------------------------------------------------

    def _on_clock_tick(self) -> None:
        clock = self.action_clock

        if clock is None or not clock.is_turn_running or self.paused:
            self._action_clock_timer.stop()
            return

        if clock.is_expired:
            self._on_time_out()
        else:
            self._update_clock_bar()

    def _on_time_out(self) -> None:
        """Both the time to act and the time bank ran out: the hand is dead."""
        hand = self._require_hand()
        legal_actions = get_legal_actions(player=self._human_player(), hand=hand)
        self._play_human_action(timeout_action(legal_actions), timed_out=True)

    def _start_clock_display(self) -> None:
        clock = self.action_clock

        if clock is None:
            return

        if not clock.is_turn_running:
            clock.start_turn()

        self.clock_bar.show()
        self._update_clock_bar()
        self._action_clock_timer.start()

    def _stop_clock_display(self) -> None:
        self._action_clock_timer.stop()
        self.clock_bar.hide()

    def _update_clock_bar(self) -> None:
        clock = self.action_clock

        if clock is None:
            return

        if clock.is_in_time_bank:
            left = clock.time_bank_left()
            total = clock.time_bank
            text = f"Time bank  {math.ceil(left)} s"
            state = "bank"
        else:
            left = clock.time_to_act_left()
            total = clock.preset.time_to_act
            text = f"{math.ceil(left)} s"
            state = "warning" if left <= WARNING_SECONDS else "normal"

        self.clock_bar.setValue(round(CLOCK_BAR_STEPS * left / total) if total else 0)
        self.clock_bar.setFormat(text)
        self.clock_bar.setProperty("state", state)
        self.clock_bar.setStyleSheet(
            f"QProgressBar::chunk {{ background-color: {CLOCK_COLORS[state]}; }}"
        )

    # --- Hands ------------------------------------------------------------------

    def _start_next_hand(self) -> None:
        if self.paused:
            return

        game = self._require_game()
        self._cancel_next_hand()

        if game.is_hand_in_progress:  # Already dealt (button and timer both).
            return
        hand = game.start_hand()
        level = game.session.blind_level

        self._logged_street_count = 0
        self._reveal_logged = False
        self.info_label.setText(
            f"HAND #{game.session.hand_number}   ·   BLINDS {level.describe()}"
        )
        self._log(f"\n── Hand #{game.session.hand_number} ──")

        for event in hand.actions:
            self._log(f"{event.player}: {describe_action(event)}")

        human = self._human_player()

        if human.hand:  # Not dealt in once out of a tournament.
            self._log(f"Your cards: {format_cards(human.hand)}")
        self._after_step()

    def _play_step(self) -> None:
        """Play one bot action or deal one street."""
        game = self._game

        if game is None or not game.is_hand_in_progress or game.is_waiting_for_human:
            return

        event = game.step()

        if event is not None:
            self._log(f"{event.player}: {describe_action(event)}")

        self._after_step()

    def _after_step(self) -> None:
        """Refresh the display and arrange for the next step."""
        game = self._require_game()
        hand = self._require_hand()

        self._log_new_streets(hand)
        self._log_reveal(hand)
        self._refresh_amounts()

        if self.account is not None:
            self.account.update_stack(self._human_player().stack)

        if self.paused:
            return

        if hand.finished:
            self._count_hand_for_clock(hand)
            self._show_hand_result(hand)
        elif game.is_waiting_for_human:
            self._enable_human_actions(hand)
        else:
            self._disable_human_actions()
            self._step_timer.start(self._next_step_delay(hand))

    def _next_step_delay(self, hand: Hand) -> int:
        """Each street of a run-out is dealt a little slower than an action."""
        if is_running_out(hand) and hand.current_player is None:
            return runout_delay_ms(self.step_delay_ms)

        return self.step_delay_ms

    def _log_reveal(self, hand: Hand) -> None:
        """Log the cards turned face up once the betting is over."""
        if self._reveal_logged or hand.revealed_after_action is None:
            return

        self._reveal_logged = True
        self._log("*** Cards revealed ***")

        for player in hand.table.players:
            if player.is_active and player.hand:
                self._log(f"{player.name}: {format_cards(player.hand)}")

    def _count_hand_for_clock(self, hand: Hand) -> None:
        """Count each finished hand once, for the time bank's top-ups."""
        if self.action_clock is not None and self._clock_counted_hand is not hand:
            self._clock_counted_hand = hand
            self.action_clock.on_hand_finished()

    def _enable_human_actions(self, hand: Hand) -> None:
        human = self._human_player()

        self.bottom_stack.setCurrentWidget(self.action_panel)
        self.action_panel.set_legal_actions(
            get_legal_actions(player=human, hand=hand),
            pot=hand.pot,
            current_bet=hand.current_bet,
            player_bet=human.current_bet,
        )
        self._start_clock_display()

    def _disable_human_actions(self) -> None:
        self.bottom_stack.setCurrentWidget(self.action_panel)
        self.action_panel.set_legal_actions((), pot=0, current_bet=0, player_bet=0)
        self._stop_clock_display()

    def _on_action_chosen(self, action: Action) -> None:
        self._play_human_action(action)

    def _play_human_action(self, action: Action, timed_out: bool = False) -> None:
        """Play the human's decision; ``timed_out`` when the clock decided."""
        game = self._game

        if game is None or not game.is_waiting_for_human or self.paused:
            return

        hand = self._require_hand()
        controller = game.controllers[self._human_name]
        assert isinstance(controller, HumanController)
        controller.submit(action)

        try:
            event = game.step()
        except IllegalActionError as error:
            # The panel only offers legal actions, so this is unexpected:
            # report it and let the player choose again.
            self._log(f"Action refused: {error}")
            self._after_step()
            return

        if self.action_clock is not None:
            self.action_clock.end_turn()

        self._stop_clock_display()

        if event is not None and timed_out:
            record_timeout(hand, event)
            self._log(f"{event.player} ran out of time — {describe_action(event)}")
        elif event is not None:
            self._log(f"{event.player}: {describe_action(event)}")

        self._after_step()

    def _log_hand_result(self, hand: Hand) -> list[str]:
        """Log the showdown and the winners; return the winner lines."""
        for name, evaluation in hand.showdown_evaluations.items():
            cards = next(p.hand for p in hand.table.players if p.name == name)
            self._log(f"{name} shows {format_cards(cards)} ({evaluation.name})")

        result_lines = describe_result(hand)

        for line in result_lines:
            self._log(line)

        return result_lines

    def _show_hand_result(self, hand: Hand) -> None:
        game = self._require_game()
        session = game.session
        human = self._human_player()
        result_lines = self._log_hand_result(hand)

        for player in hand.table.players:
            if player.is_eliminated and player.total_contribution > 0:
                self._log(f"{player.name} is eliminated")

        opponents_left = sum(
            1 for player in session.get_players_with_chips() if player is not human
        )

        can_rebuy = self._can_pay_rebuy()

        if opponents_left == 0:
            result_lines.append("You win the game!")
        elif human.is_busted and not can_rebuy:
            result_lines.append("Out of chips: your bankroll cannot pay a rebuy.")
        elif human.is_busted:
            result_lines.append("You are out of chips.")

        self.result_label.setText("   ·   ".join(result_lines))
        self.rebuy_button.setText(f"Rebuy {session.config.rebuy_stack}")
        self.rebuy_button.setVisible(
            human.is_busted and opponents_left > 0 and can_rebuy
        )
        can_continue = not human.is_busted and opponents_left > 0
        self.next_hand_button.setVisible(can_continue)
        self.bottom_stack.setCurrentIndex(1)

        if can_continue:
            self._schedule_next_hand()

    def _can_pay_rebuy(self) -> bool:
        if self.account is None:
            return True

        return self.account.can_pay(self._require_game().session.config.rebuy_stack)

    def _on_rebuy_clicked(self) -> None:
        game = self._require_game()

        if self.account is not None:
            self.account.pay(TransactionType.REBUY, game.session.config.rebuy_stack)

        game.session.rebuy_player(self._human_player())
        self._log(f"{self._human_name} rebuys {game.session.config.rebuy_stack}")
        self._start_next_hand()

    def _on_menu_clicked(self) -> None:
        self.stop()
        self.menu_requested.emit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_game(self) -> TableGame:
        if self._game is None:
            raise RuntimeError("No game has been started.")

        return self._game

    def _require_hand(self) -> Hand:
        hand = self._require_game().hand

        if hand is None:
            raise RuntimeError("No hand has been started.")

        return hand

    def _human_player(self) -> Player:
        players = self._require_game().session.players

        return next(player for player in players if player.name == self._human_name)

    def _log_new_streets(self, hand: Hand) -> None:
        """Log the streets dealt since the last refresh."""
        for street_event in hand.streets[self._logged_street_count :]:
            if street_event.community_cards:
                self._log(
                    f"*** {street_event.street} *** "
                    f"{format_cards(street_event.community_cards)}"
                )

        self._logged_street_count = len(hand.streets)

    def _log(self, text: str) -> None:
        self.history_view.appendPlainText(text)
