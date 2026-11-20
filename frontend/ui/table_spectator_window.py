"""Watch another table of your tournament while you play (V3.1.1).

The window follows one live table: the bots' hands as they are played, with
a short history. You only watch: the cards stay face down as at your own
table (the "Bots' cards" setting applies), and nothing you do here changes
the game. When the table breaks, the window says so.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from backend.application.profile import BotCards
from backend.application.tournament import Tournament, TournamentTable
from backend.poker_engine.models import Hand
from frontend.components.hand_history import HISTORY_WIDTH, HandHistoryView, Tone
from frontend.components.table_widget import TableWidget
from frontend.formatting import describe_result, format_cards

from .game_screen import bot_styles, build_table_state

WINDOW_SIZE = (900, 560)


class TableSpectatorWindow(QWidget):
    """One table of a running tournament, watched from its own window."""

    def __init__(self, tournament: Tournament, number: int, title: str) -> None:
        super().__init__()
        self.setObjectName("guideWindow")  # The application's dark background.
        self.setWindowTitle(f"Table {number} · {title}")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.resize(*WINDOW_SIZE)
        self.tournament = tournament
        self.number = number
        self.bot_cards = BotCards.SHOWDOWN
        self.in_big_blinds = False
        self.show_styles = False
        self._hand: Hand | None = None
        self._logged_actions = 0
        self._logged_streets = 0
        self._result_logged = False
        self._state: tuple[object, ...] | None = None

        self.info_label = QLabel()
        self.info_label.setObjectName("sectionTitle")
        self.table_widget = TableWidget()
        self.history_view = HandHistoryView()
        self.history_view.setFixedWidth(HISTORY_WIDTH)

        body = QHBoxLayout()
        body.addWidget(self.table_widget, stretch=1)
        body.addWidget(self.history_view)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        layout.addWidget(self.info_label)
        layout.addLayout(body, stretch=1)

    @property
    def table(self) -> TournamentTable | None:
        """The watched table; None once it broke."""
        return next(
            (table for table in self.tournament.tables if table.number == self.number),
            None,
        )

    def follow(self, tournament: Tournament) -> None:
        """Watch the same table number of another tournament (played again)."""
        self.tournament = tournament
        self._hand = None
        self._state = None
        self.history_view.clear()
        self.refresh()

    def set_display(
        self, bot_cards: BotCards, in_big_blinds: bool, show_styles: bool = False
    ) -> None:
        """The table settings of your own table."""
        display = (bot_cards, in_big_blinds, show_styles)

        if display != (self.bot_cards, self.in_big_blinds, self.show_styles):
            self.bot_cards, self.in_big_blinds, self.show_styles = display
            self._state = None
            self.refresh()

    def refresh(self) -> None:
        """Show what changed at the table since the last refresh."""
        table = self.table

        if table is None:
            self.info_label.setText(
                f"TABLE {self.number}   ·   the table broke up: its players "
                "moved to other tables"
                if not self.tournament.is_finished
                else f"TABLE {self.number}   ·   the tournament is over"
            )
            return

        hand = table.hand
        state = (
            id(hand),
            None if hand is None else len(hand.actions),
            None if hand is None else len(hand.streets),
            None if hand is None else hand.finished,
            len(table.session.players),
        )

        if state == self._state:
            return

        self._state = state
        in_progress = hand is not None and not hand.finished
        number = table.hands_played + int(in_progress)
        parts = [f"TABLE {self.number}", f"HAND #{number}"]

        if hand is not None and hand.blind_level is not None:
            parts.append(f"BLINDS {hand.blind_level.describe()}")

        if self.tournament.hand_for_hand:
            parts.append("HAND-FOR-HAND")

        self.info_label.setText("   ·   ".join(parts))

        if hand is None:
            return

        self._log(hand, number)
        self.table_widget.set_state(
            build_table_state(
                hand,
                human_name=None,
                in_big_blinds=self.in_big_blinds,
                bot_cards=self.bot_cards,
                styles=(
                    bot_styles(self.tournament.controllers)
                    if self.show_styles
                    else None
                ),
            )
        )

    def _log(self, hand: Hand, number: int) -> None:
        history = self.history_view

        if hand is not self._hand:
            self._hand = hand
            self._logged_actions = 0
            self._logged_streets = 0
            self._result_logged = False
            level = hand.blind_level
            history.start_hand(number, level.describe() if level is not None else "")

        for event in hand.actions[self._logged_actions :]:
            history.add_action(event)

        self._logged_actions = len(hand.actions)

        for street in hand.streets[max(1, self._logged_streets) :]:
            board = street.community_cards
            history.add_section(
                street.street.capitalize(),
                board,
                line=f"*** {street.street} *** {format_cards(board)}",
            )

        self._logged_streets = len(hand.streets)

        if hand.finished and not self._result_logged:
            self._result_logged = True

            for line in describe_result(hand):
                history.add_note(line, Tone.RESULT)
