"""The table of a Tournament or a Spin & Go played by the user.

It extends the cash game screen with what a tournament needs: the blind
level and the next one, the players left, your place and the average stack,
short elimination notices, rebuy and add-on prompts, a Pause that freezes a
timed level clock, the Spin & Go multiplier reveal, and what to do once you
are out: watch the rest, skip to the results, or go back to the menu.

On several tables (V3.1) it shows table 1, yours, with the players moving
in and out, and a Lobby button opens the tournament's lobby. Once you are
out, the rest is played in short steps (the window stays responsive), and
leaving keeps your place and prize when nothing can change them anymore.
"""

import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from backend.application.action_clock import ClockPreset
from backend.application.bankroll import GameAccount, TransactionType
from backend.application.game_modes import GameMode
from backend.application.payouts import FAIR_MULTIPLIERS
from backend.application.persistence import save_session
from backend.application.tournament import Tournament
from backend.poker_engine.models import Hand, Player
from frontend.components.hand_history import Tone
from frontend.sounds import Sound, spin_prize_sound

from .game_screen import GameScreen

NOTICE_MS = 3500
REVEAL_TICKS = 14
REVEAL_TICK_MS = 90
REVEAL_HOLD_MS = 1600
REVEAL_VALUES = tuple(entry.value for entry in FAIR_MULTIPLIERS.entries)
"""Values flashed before the drawn multiplier lands."""
PLAY_OUT_TICK_SECONDS = 0.04
"""Rounds played per step of a play-out, before the window repaints."""
PLAY_OUT_REFRESH_SECONDS = 0.5
"""How often the lobby follows a play-out."""


def ordinal(place: int) -> str:
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(place if place < 20 else place % 10, "th")

    return f"{place}{suffix}"


def confirm_leave(parent: QWidget) -> bool:
    """Ask before leaving a running tournament (the buy-in is lost)."""
    if not parent.isVisible():  # Nobody to ask: a window closed by code.
        return True

    answer = QMessageBox.question(
        parent,
        "Leave the tournament",
        "Leave the tournament? You forfeit it: your buy-in is lost.",
    )

    return answer == QMessageBox.StandardButton.Yes


def format_seconds(seconds: float) -> str:
    whole = max(0, int(seconds))

    return f"{whole // 60}:{whole % 60:02d}"


def level_parts(tournament: Tournament) -> list[str]:
    """'LEVEL 3: 50/100' and when the next level comes."""
    level = tournament.level
    structure = tournament.config.structure
    parts = [f"LEVEL {tournament.level_index + 1}: {level.describe()}"]
    remaining = tournament.next_level_in()

    if remaining is None:
        parts.append("last level")
    else:
        following = structure.level(tournament.level_index + 1).describe()

        if tournament.clock is not None:
            parts.append(f"next {following} in {format_seconds(remaining)}")
        else:
            hands = int(remaining)
            parts.append(f"next {following} in {hands} hand{'s' * (hands != 1)}")

    return parts


def table_part(tournament: Tournament) -> str | None:
    """'TABLE 1 of 4', 'FINAL TABLE', or None for a one-table tournament."""
    if not tournament.multi_table:
        return None

    if len(tournament.tables) == 1:
        return "FINAL TABLE"

    return f"TABLE 1 of {len(tournament.tables)}"


class TournamentScreen(GameScreen):
    """Plays a ``Tournament`` with one human player."""

    finished = Signal(object)
    """Emitted with the finished ``Tournament`` when the user opens the results."""
    lobby_requested = Signal()
    standings_changed = Signal()
    """The stacks, places or tables changed (between hands): for the lobby."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.save_path: Path | None = None
        self.spectating = False
        self._announced = 0
        self._announced_moves = 0
        self._final_table_announced = False
        self._reveal_values: list[int] = []
        self._revealing = False
        self.tournament_account: GameAccount | None = None
        """The tournament's money in the bankroll (None: not paid for)."""
        self.confirm_leave: Callable[[QWidget], bool] = confirm_leave

        self.status_label = QLabel()
        self.status_label.setObjectName("statusText")
        # A long line is cut on a narrow table rather than widening it.
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.notice_label = QLabel()
        self.notice_label.setObjectName("noticeText")
        self.notice_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notice_label.hide()
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self.notice_label.hide)

        self.pause_button.setToolTip("Freezes the clocks and the bots.")

        self.reveal_label = QLabel()
        self.reveal_label.setObjectName("revealText")
        self.reveal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reveal_label.hide()
        self._reveal_timer = QTimer(self)
        self._reveal_timer.timeout.connect(self._reveal_tick)
        self._reveal_hold_timer = QTimer(self)
        self._reveal_hold_timer.setSingleShot(True)
        self._reveal_hold_timer.timeout.connect(self.finish_reveal)
        self._watch_timer = QTimer(self)
        """The pause between two hands while you watch the rest."""
        self._watch_timer.setSingleShot(True)
        self._watch_timer.timeout.connect(self._continue_watching)

        self._level_timer = QTimer(self)
        """Refreshes the time left in a level by time, every second."""
        self._level_timer.setInterval(1000)
        self._level_timer.timeout.connect(self._refresh_status)
        self._play_out_timer = QTimer(self)
        """Plays the rest of a multi-table tournament in short steps."""
        self._play_out_timer.setInterval(0)
        self._play_out_timer.timeout.connect(self._play_out_tick)
        self._play_out_refreshed = 0.0

        self.lobby_button = QPushButton("Lobby")
        self.lobby_button.setObjectName("small")
        self.lobby_button.setToolTip(
            "The tournament's lobby: players, tables, payouts and levels."
        )
        self.lobby_button.clicked.connect(self.lobby_requested)

        self._build_tournament_page()
        self._insert_tournament_widgets()

    # --- Layout -------------------------------------------------------------

    def _build_tournament_page(self) -> None:
        self.outcome_label = QLabel()
        self.outcome_label.setObjectName("resultText")
        self.outcome_label.setWordWrap(True)

        def button(text: str, name: str = "") -> QPushButton:
            widget = QPushButton(text)
            widget.setMinimumHeight(48)
            widget.setMinimumWidth(130)

            if name:
                widget.setObjectName(name)

            return widget

        self.continue_button = button("Next hand", "primary")
        self.continue_button.clicked.connect(self._start_next_hand)
        self.tournament_rebuy_button = button("Rebuy", "accent")
        self.tournament_rebuy_button.clicked.connect(self._on_tournament_rebuy)
        self.decline_button = button("Leave")
        self.decline_button.clicked.connect(self._on_decline_rebuy)
        self.add_on_button = button("Add-on", "accent")
        self.add_on_button.clicked.connect(self._on_add_on)
        self.watch_button = button("Watch", "accent")
        self.watch_button.clicked.connect(self.watch_rest)
        self.skip_button = button("Skip to results", "primary")
        self.skip_button.clicked.connect(self.skip_to_results)
        self.results_button = button("See the results", "primary")
        self.results_button.clicked.connect(self._open_results)
        self.leave_button = button("Back to menu")
        self.leave_button.clicked.connect(self._on_menu_clicked)

        self.tournament_buttons = (
            self.tournament_rebuy_button,
            self.decline_button,
            self.add_on_button,
            self.watch_button,
            self.skip_button,
            self.results_button,
            self.leave_button,
            self.continue_button,
        )

        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.outcome_label, stretch=1)

        for widget in self.tournament_buttons:
            layout.addWidget(widget)

        self.tournament_page = page
        self.bottom_stack.addWidget(page)
        self._set_buttons()

    def _insert_tournament_widgets(self) -> None:
        """Put the status bar, notices and reveal above the table."""
        left = self.left_layout
        status_bar = QHBoxLayout()
        status_bar.addWidget(self.status_label, stretch=1)
        status_bar.addWidget(self.lobby_button)
        left.insertLayout(0, status_bar)
        left.insertWidget(1, self.notice_label)
        # While it shows, the reveal takes the table's place.
        left.insertWidget(2, self.reveal_label, stretch=1)
        self.menu_button.setText("Leave")

    # --- Flow ---------------------------------------------------------------

    @property
    def tournament(self) -> Tournament:
        game = self._require_game()
        assert isinstance(game, Tournament)

        return game

    def start_tournament(
        self,
        tournament: Tournament,
        human_name: str,
        save_path: Path | None = None,
        clock: ClockPreset | None = None,
        account: GameAccount | None = None,
    ) -> None:
        """Start playing; a Spin & Go first reveals its prize multiplier.

        ``clock`` is the human's action clock (None: no clock). ``account``
        pays the rebuys and the add-on, and receives the prize at the end.
        """
        self.save_path = save_path
        self.tournament_account = account
        self.spectating = False
        self._announced = 0
        self._announced_moves = 0
        self._final_table_announced = False
        self.lobby_button.setVisible(tournament.multiplier is None)
        self._notice_timer.stop()
        self.notice_label.hide()
        self.status_label.clear()

        if tournament.multiplier is None:
            self.start_game(tournament, human_name, clock)
        else:
            self._game = tournament
            self._human_name = human_name
            self._set_clock(clock)
            self.history_view.clear()
            self._start_reveal(tournament)

        if tournament.clock is not None:
            self._level_timer.start()

    def stop(self) -> None:
        """Stop every timer; an unfinished tournament is forfeited, a finished
        one paid. Called when leaving the screen and when the window closes."""
        self.stop_timers()
        self._notice_timer.stop()
        account = self.tournament_account

        if account is not None and not account.closed and self._game is not None:
            if self.tournament.is_finished:
                self._settle_account()
            else:
                account.forfeit()

        self.tournament_account = None
        super().stop()

    def _can_pay(self) -> bool:
        """Whether the bankroll can pay one more buy-in (rebuy or add-on)."""
        account = self.tournament_account

        return account is None or account.can_pay(self.tournament.config.buy_in)

    def _settle_account(self) -> None:
        """Credit the prize once the tournament is over (only once)."""
        account = self.tournament_account

        if account is None or account.closed or not self.tournament.is_finished:
            return

        account.finish(self.tournament.result.finish_of(self._human_name).prize)

    def prepare_to_leave(self) -> bool:
        """Get ready to leave; False if the user chose to stay.

        Once out, the rest of the tournament is played instantly, so the
        prize is known; leaving while still in asks first, then forfeits.
        """
        game = self._game

        if not isinstance(game, Tournament) or game.is_finished:
            return True

        name = self._human_name

        if game.is_waiting_for_rebuy and game.can_rebuy(name):
            game.decline_rebuy(name)

        if self._human_player().is_eliminated:
            if game.multi_table and game.known_prize(name) is not None:
                self._leave_with_known_prize()
            else:
                self._play_out()

            return True

        return self.confirm_leave(self)

    def _leave_with_known_prize(self) -> None:
        """Out of a multi-table tournament: keep your place and prize, and
        save the standings so far, without playing the rest."""
        tournament = self.tournament
        self.stop_timers()
        prize = tournament.known_prize(self._human_name)
        account = self.tournament_account

        if account is not None and not account.closed and prize is not None:
            account.finish(prize)

        self._save(standings=True)

    def _on_menu_clicked(self) -> None:
        if self.prepare_to_leave():
            super()._on_menu_clicked()

    def _start_next_hand(self) -> None:
        game = self._game

        if game is None or self.paused:
            return

        tournament = self.tournament

        if tournament.is_finished:
            self._show_finished()
            return

        super()._start_next_hand()
        self._log_new_eliminations()
        self._log_table_changes()
        self._refresh_status()
        self.standings_changed.emit()

    def _human_player(self) -> Player:
        """You, at your table or out of the tournament (no longer seated)."""
        return self.tournament.player(self._human_name)

    def _after_step(self) -> None:
        super()._after_step()
        self._refresh_status()

    def _show_hand_result(self, hand: Hand) -> None:
        tournament = self.tournament
        lines = self._log_hand_result(hand)
        self._log_new_eliminations()
        self._save()
        self.standings_changed.emit()

        if tournament.is_finished:
            self._show_finished(lines)
            return

        if self.spectating:
            self._set_buttons()
            self.outcome_label.setText("   ·   ".join(lines))
            self.bottom_stack.setCurrentWidget(self.tournament_page)
            self._step_timer.stop()
            self._watch_timer.start(self.hand_pause_ms)
            return

        human = self._human_player()
        name = self._human_name

        if tournament.is_waiting_for_rebuy and tournament.can_rebuy(name):
            if not self._can_pay():
                lines.append("Out of chips: your bankroll cannot pay a rebuy.")
                self._show_page(lines, self.decline_button)
                return

            lines.append("You are out of chips: rebuy or leave the tournament.")
            self._show_page(lines, self.tournament_rebuy_button, self.decline_button)
            self._label_rebuy()
            return

        if human.is_eliminated:
            self._show_bust(lines)
            return

        shown = [self.continue_button]

        if tournament.can_add_on(name) and self._can_pay():
            shown.append(self.add_on_button)
            rules = tournament.config.rebuys
            assert rules is not None
            self.add_on_button.setText(f"Add-on +{rules.add_on_stack}")

        if tournament.can_rebuy(name) and self._can_pay():
            shown.append(self.tournament_rebuy_button)
            self._label_rebuy()

        self._show_page(lines, *shown)

        # The add-on is offered once: wait for the user's choice. An optional
        # rebuy stays available while the result is shown.
        if self.add_on_button not in shown:
            self._schedule_next_hand()

    def _show_bust(self, lines: list[str]) -> None:
        tournament = self.tournament
        place = tournament.current_place(self._human_name)
        prize = tournament.prize_for_place(place)
        lines.append(
            f"You finished {ordinal(place)}" + (f", prize {prize}." if prize else ".")
        )
        self._show_page(lines, self.watch_button, self.skip_button, self.leave_button)

    def _show_finished(self, lines: list[str] | None = None) -> None:
        tournament = self.tournament
        result = tournament.result
        winner = result.winner
        lines = list(lines or [])
        you = result.finish_of(self._human_name)

        if winner.name == self._human_name:
            lines.append(f"You win the tournament: {winner.prize}!")
        else:
            lines.append(
                f"{winner.name} wins the tournament. You finished {ordinal(you.place)}."
            )

        self._level_timer.stop()
        self._step_timer.stop()
        self._cancel_next_hand()
        self._save()
        self._settle_account()
        self._show_page(lines, self.results_button, self.leave_button)

    def _show_page(self, lines: list[str], *buttons: QPushButton) -> None:
        self.outcome_label.setText("   ·   ".join(lines))
        self._set_buttons(*buttons)
        self.bottom_stack.setCurrentWidget(self.tournament_page)

    def _set_buttons(self, *shown: QPushButton) -> None:
        for widget in self.tournament_buttons:
            widget.setVisible(widget in shown)

    def _label_rebuy(self) -> None:
        rules = self.tournament.config.rebuys
        assert rules is not None
        self.tournament_rebuy_button.setText(
            f"Rebuy +{rules.rebuy_stack} ({self.tournament.config.buy_in})"
        )

    # --- Decisions after a hand ---------------------------------------------

    def _on_tournament_rebuy(self) -> None:
        tournament = self.tournament

        if self.tournament_account is not None:
            self.tournament_account.pay(TransactionType.REBUY, tournament.config.buy_in)

        tournament.rebuy(self._human_name)
        self._log(f"{self._human_name} rebuys")
        self._refresh_status()
        self.standings_changed.emit()

        if tournament.is_finished:
            self._show_finished()
        else:
            self._start_next_hand()

    def _on_decline_rebuy(self) -> None:
        tournament = self.tournament
        tournament.decline_rebuy(self._human_name)
        self._log_new_eliminations()
        self._refresh_status()
        self.standings_changed.emit()

        if tournament.is_finished:
            self._show_finished()
        else:
            self._show_bust([])

    def _on_add_on(self) -> None:
        if self.tournament_account is not None:
            self.tournament_account.pay(
                TransactionType.ADD_ON, self.tournament.config.buy_in
            )

        self.tournament.add_on(self._human_name)
        self._log(f"{self._human_name} takes the add-on")
        self.add_on_button.hide()
        self._refresh_status()
        self.standings_changed.emit()
        self._schedule_next_hand()

    def watch_rest(self) -> None:
        """Keep the table playing without you, at the chosen speed."""
        self.spectating = True
        self._set_buttons(self.skip_button, self.leave_button)
        self._continue_watching()

    def _continue_watching(self) -> None:
        if self._game is None or not self.spectating or self.paused:
            return

        tournament = self.tournament

        if tournament.is_finished:
            self._show_finished()
        elif not tournament.is_hand_in_progress:
            self._start_next_hand()
            self._set_buttons(self.skip_button, self.leave_button)

    def skip_to_results(self) -> None:
        """Play the rest instantly (same hands as watching) and show the results.

        Only once you are out: nobody can decide for you.
        """
        tournament = self.tournament

        if not tournament.is_finished and not self._human_player().is_eliminated:
            raise RuntimeError("Skip to results is only possible once you are out.")

        if tournament.multi_table and not tournament.is_finished:
            self._start_play_out()
            return

        self._play_out()
        self._open_results()

    @property
    def is_playing_out(self) -> bool:
        return self._play_out_timer.isActive()

    def _start_play_out(self) -> None:
        """Play the rest of a multi-table tournament in short steps, then
        open the results."""
        self.spectating = False
        self.stop_timers()
        self._finish_current_hand()
        self._set_buttons(self.leave_button)
        self.bottom_stack.setCurrentWidget(self.tournament_page)
        self._play_out_refreshed = time.monotonic()
        self._play_out_timer.start()
        self._play_out_tick()

    def _play_out_tick(self) -> None:
        tournament = self.tournament
        deadline = time.monotonic() + PLAY_OUT_TICK_SECONDS

        while not tournament.is_finished and time.monotonic() < deadline:
            tournament.play_round()

        left = len(tournament.players_left())
        self.outcome_label.setText(f"Finishing the tournament: {left} players left…")

        if not tournament.is_finished:
            if time.monotonic() - self._play_out_refreshed >= PLAY_OUT_REFRESH_SECONDS:
                self._play_out_refreshed = time.monotonic()
                self.standings_changed.emit()

            return

        self._play_out_timer.stop()
        self._announced = len(tournament.eliminations)
        self._save()
        self._settle_account()
        self.standings_changed.emit()
        self._open_results()

    def _finish_current_hand(self) -> None:
        hand = self.tournament.hand

        if hand is not None:
            while not hand.finished:
                self.tournament.step()

    def _play_out(self) -> None:
        """Play the rest of the tournament instantly (you are out)."""
        tournament = self.tournament
        self._step_timer.stop()
        self._play_out_timer.stop()
        self._finish_current_hand()
        tournament.play_to_end()
        self._log_new_eliminations()
        self._save()
        self._settle_account()

    def _open_results(self) -> None:
        self.stop_timers()
        self._settle_account()
        self.finished.emit(self.tournament)

    def stop_timers(self) -> None:
        self._step_timer.stop()
        self._cancel_next_hand()
        self._stop_clock_display()
        self._level_timer.stop()
        self._reveal_timer.stop()
        self._reveal_hold_timer.stop()
        self._watch_timer.stop()
        self._play_out_timer.stop()

    def _on_pause_changed(self) -> None:
        """Also freeze the level clock; resume watching once restarted."""
        tournament = self.tournament

        if tournament.clock is not None:
            if self.paused:
                tournament.clock.pause()
            else:
                tournament.clock.resume()

        super()._on_pause_changed()

        if not self.paused and not tournament.is_hand_in_progress:
            self._continue_watching()

        self._refresh_status()

    # --- Display ------------------------------------------------------------

    def _refresh_status(self) -> None:
        if self._game is None:
            return

        tournament = self.tournament
        parts = level_parts(tournament)
        table = table_part(tournament)

        if table is not None:
            parts.insert(0, table)

        left = tournament.players_left()
        average = tournament.average_stack() / tournament.level.big_blind
        multi_table = tournament.multi_table

        if multi_table:  # The lobby has the rest.
            parts.append(f"{len(left)}/{tournament.entrants} left")
        else:
            parts.append(f"{len(left)} players left")

        if not self._human_player().is_eliminated:
            place = tournament.current_place(self._human_name)
            parts.append(f"you are {ordinal(place)}")

        parts.append(f"average {average:.1f} bb")

        if not multi_table:
            parts.append(f"prize pool {tournament.prize_pool}")

        self.status_label.setToolTip("   ·   ".join(parts))

        if self.paused:
            parts.append("PAUSED")

        self.status_label.setText("   ·   ".join(parts))

    def _log_new_eliminations(self) -> None:
        """The players out since the last time. On several tables: only
        those of your table, and the others once in the money."""
        tournament = self.tournament
        notices = []

        for elimination in tournament.eliminations[self._announced :]:
            for name, prize in zip(elimination.names, elimination.prizes, strict=True):
                if (
                    tournament.multi_table
                    and not prize
                    and not self._at_your_table(name)
                ):
                    continue

                text = f"{name} is out in {ordinal(elimination.place)} place"
                text += f" and wins {prize}" if prize else ""
                self._log(text, Tone.ALERT)
                notices.append(text)

        self._announced = len(tournament.eliminations)

        if notices:
            self.show_notice("   ·   ".join(notices))

    def _at_your_table(self, name: str) -> bool:
        table = self.tournament.table_of(name)

        return table is not None and table.number == 1

    def _log_table_changes(self) -> None:
        """The players moving in and out of your table, the final table."""
        tournament = self.tournament

        for move in tournament.table_moves[self._announced_moves :]:
            if move.to_table == 1:
                self._log(f"{move.name} joins from table {move.from_table}")
            elif move.from_table == 1:
                self._log(f"{move.name} moves to table {move.to_table}")

        self._announced_moves = len(tournament.table_moves)
        final = tournament.final_table_hand

        if final is not None and not self._final_table_announced:
            self._final_table_announced = True
            self._log("Final table!", Tone.ALERT)
            self.show_notice(
                f"FINAL TABLE — {len(tournament.players_left())} players left"
            )

    def show_notice(self, text: str) -> None:
        """A short message above the table that hides itself."""
        self.notice_label.setText(text)
        self.notice_label.show()
        self._notice_timer.start(NOTICE_MS)

    def _save(self, standings: bool = False) -> None:
        """Save the hands and, once finished, the results; ``standings``
        saves the results so far (you left once out)."""
        if self.save_path is None:
            return

        tournament = self.tournament

        if tournament.is_finished:
            result = tournament.result.to_dict()
        else:
            result = tournament.standings() if standings else None
        mode = GameMode.SPIN if tournament.multiplier else GameMode.TOURNAMENT
        save_session(
            tournament.session,
            self.save_path,
            tournament=result,
            human=self._human_name,
            mode=mode,
        )

    # --- Spin & Go reveal ---------------------------------------------------

    def _start_reveal(self, tournament: Tournament) -> None:
        assert tournament.multiplier is not None
        self._reveal_values = [
            REVEAL_VALUES[index % len(REVEAL_VALUES)] for index in range(REVEAL_TICKS)
        ]
        self._reveal_values.append(tournament.multiplier.value)
        self._revealing = True
        self.info_label.setText("SPIN & GO")
        self.table_widget.hide()
        self.reveal_label.show()
        self._set_buttons()
        self.bottom_stack.setCurrentWidget(self.tournament_page)
        self.outcome_label.setText("Drawing the prize multiplier…")
        self._reveal_timer.start(REVEAL_TICK_MS)

    def _reveal_tick(self) -> None:
        if not self._reveal_values:
            return

        value = self._reveal_values.pop(0)
        self.reveal_label.setText(f"× {value}")

        if self._reveal_values:
            self.sounds.play(Sound.SPIN_TICK)
        else:
            self.sounds.play(spin_prize_sound(value))
            self._reveal_timer.stop()
            tournament = self.tournament
            self.reveal_label.setText(
                f"× {value}   —   PRIZE POOL {tournament.prize_pool}"
            )
            self.outcome_label.setText(f"Prize pool: {tournament.prize_pool}")
            self._reveal_hold_timer.start(REVEAL_HOLD_MS)

    @property
    def is_revealing(self) -> bool:
        return self._revealing

    def finish_reveal(self) -> None:
        """End the multiplier reveal (or skip it) and deal the first hand."""
        if self._game is None or self.tournament.hand is not None:
            return

        self._reveal_timer.stop()
        self._reveal_values = []
        self._revealing = False
        multiplier = self.tournament.multiplier
        assert multiplier is not None
        self._log(
            f"Prize multiplier: × {multiplier.value} — "
            f"prize pool {self.tournament.prize_pool}",
            Tone.RESULT,
        )
        self.reveal_label.hide()
        self.table_widget.show()
        self._start_next_hand()
