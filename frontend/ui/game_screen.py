"""The game screen: table, action panel and hand history.

The screen never runs a blocking game loop. Each bot action or street is one
short step triggered by a timer, and the human acts through the action panel.
"""

from collections.abc import Mapping
from typing import Protocol

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.application.controllers import HumanController, PlayerController
from backend.poker_engine.actions import Action
from backend.poker_engine.betting import IllegalActionError, get_legal_actions
from backend.poker_engine.models import ActionEvent, Hand, Player
from backend.poker_engine.session import GameSession
from frontend.components.action_panel import ActionPanel
from frontend.components.seat_widget import SeatHighlight, SeatState
from frontend.components.table_widget import TableState, TableWidget
from frontend.formatting import describe_action, describe_result, format_cards

DEFAULT_STEP_DELAY_MS = 800


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


def player_status(player: Player, hand: Hand) -> str:
    """Return the short status line shown under a player's stack."""
    if player.is_eliminated:
        return "Out"

    if hand.finished and player.name in hand.payouts:
        return f"Wins {hand.payouts[player.name]}"

    if player.folded:
        return "Folded"

    if player.all_in:
        return "All-in"

    return player.position or ""


def build_table_state(
    hand: Hand, human_name: str | None, show_all_cards: bool = False
) -> TableState:
    """Translate the engine state into what the table displays.

    Seats are rotated so the human sits at the bottom; a spectator (no human)
    sees the first seat at the bottom. Other players' cards stay face down
    unless they reached the showdown, or ``show_all_cards`` is set.
    """
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

        shows_cards = (
            show_all_cards
            or player.name == human_name
            or player.name in hand.showdown_evaluations
        )

        seats.append(
            SeatState(
                name=player.name,
                stack=player.stack,
                cards=tuple(player.hand),
                cards_face_up=shows_cards,
                status=player_status(player, hand),
                highlight=highlight,
                dimmed=player.folded,
            )
        )

    return TableState(
        seats=tuple(seats),
        bets=tuple(player.current_bet for player in ordered),
        dealer_seat=ordered.index(hand.table.dealer),
        community_cards=tuple(hand.community_cards),
        pot=hand.pot,
    )


class GameScreen(QWidget):
    """Plays a game and displays its state."""

    menu_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.step_delay_ms = DEFAULT_STEP_DELAY_MS
        self._game: TableGame | None = None
        self._human_name = ""
        self._logged_street_count = 0

        self._step_timer = QTimer(self)
        self._step_timer.setSingleShot(True)
        self._step_timer.timeout.connect(self._play_step)

        self.info_label = QLabel()
        self.info_label.setObjectName("sectionTitle")
        self.menu_button = QPushButton("Menu")
        self.menu_button.setObjectName("small")
        self.menu_button.clicked.connect(self._on_menu_clicked)

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
        top_bar.addWidget(self.menu_button)

        bottom_panel = QFrame()
        bottom_panel.setObjectName("panel")
        bottom_layout = QVBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(16, 12, 16, 12)
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

    def start_game(self, game: TableGame, human_name: str) -> None:
        """Start playing a new game with the given human player."""
        if not isinstance(game.controllers.get(human_name), HumanController):
            raise ValueError(f"{human_name} is not controlled by a human.")

        self._step_timer.stop()
        self._game = game
        self._human_name = human_name
        self.history_view.clear()
        self._start_next_hand()

    def stop(self) -> None:
        """Stop the game in progress, if any."""
        self._step_timer.stop()
        self._game = None

    def _start_next_hand(self) -> None:
        game = self._require_game()
        hand = game.start_hand()
        level = game.session.blind_level

        self._logged_street_count = 0
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
        self.table_widget.set_state(build_table_state(hand, self._human_name))

        if hand.finished:
            self._show_hand_result(hand)
        elif game.is_waiting_for_human:
            self._enable_human_actions(hand)
        else:
            self._disable_human_actions()
            self._step_timer.start(self.step_delay_ms)

    def _enable_human_actions(self, hand: Hand) -> None:
        human = self._human_player()

        self.bottom_stack.setCurrentWidget(self.action_panel)
        self.action_panel.set_legal_actions(
            get_legal_actions(player=human, hand=hand),
            pot=hand.pot,
            current_bet=hand.current_bet,
            player_bet=human.current_bet,
        )

    def _disable_human_actions(self) -> None:
        self.bottom_stack.setCurrentWidget(self.action_panel)
        self.action_panel.set_legal_actions((), pot=0, current_bet=0, player_bet=0)

    def _on_action_chosen(self, action: Action) -> None:
        game = self._game

        if game is None or not game.is_waiting_for_human:
            return

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

        if event is not None:
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

        if opponents_left == 0:
            result_lines.append("You win the game!")
        elif human.is_busted:
            result_lines.append("You are out of chips.")

        self.result_label.setText("   ·   ".join(result_lines))
        self.rebuy_button.setText(f"Rebuy {session.config.rebuy_stack}")
        self.rebuy_button.setVisible(human.is_busted and opponents_left > 0)
        self.next_hand_button.setVisible(not human.is_busted and opponents_left > 0)
        self.bottom_stack.setCurrentIndex(1)

    def _on_rebuy_clicked(self) -> None:
        game = self._require_game()
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
