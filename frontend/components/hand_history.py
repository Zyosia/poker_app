"""The hand history beside a table: one block per hand, cards drawn as cards.

Each hand shows its number and blinds, your cards, then every street with
its board and the actions in two columns (who, what), the cards shown and
the result. The actions are coloured by kind (fold, check or call, bet or
raise, all-in), so the history reads at a glance.

``text()`` returns the same history as plain lines (tests, copying).
"""

from collections import deque
from collections.abc import Callable, Sequence
from enum import StrEnum

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from backend.poker_engine.constants import ActionType, Card
from backend.poker_engine.models import ActionEvent
from frontend.formatting import describe_action

from .card_widget import CardWidget

CARD_SIZE = QSize(24, 34)
NAME_WIDTH = 92
MAX_HANDS = 40
"""Older hands are dropped from the view (the session file keeps them)."""
MAX_LINES = 5000
HISTORY_WIDTH = 290


class Tone(StrEnum):
    """How a line is coloured (see the ``history*`` styles of the theme)."""

    POST = "post"
    FOLD = "fold"
    PASSIVE = "passive"
    AGGRESSIVE = "aggressive"
    ALL_IN = "allIn"
    RESULT = "result"
    NOTE = "note"
    ALERT = "alert"


def action_tone(event: ActionEvent) -> Tone:
    if event.action.startswith("post_"):
        return Tone.POST

    if event.action == ActionType.FOLD:
        return Tone.FOLD

    if event.action == ActionType.ALL_IN:
        return Tone.ALL_IN

    if event.action in (ActionType.CHECK, ActionType.CALL):
        return Tone.PASSIVE

    return Tone.AGGRESSIVE


def _label(text: str, name: str, tone: Tone | None = None) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)

    if tone is not None:
        label.setProperty("tone", tone.value)

    return label


def _cards(cards: Sequence[Card]) -> list[CardWidget]:
    widgets = []

    for card in cards:
        widget = CardWidget(CARD_SIZE)
        widget.set_card(card)
        widgets.append(widget)

    return widgets


HistoryEntry = Callable[["HandHistoryView"], None]
"""One line of a history, written later (the replayer rebuilds its history
step by step)."""


class HandHistoryView(QScrollArea):
    """The history of the hands played at a table."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("handHistory")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("handHistoryContent")
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(8)
        self._layout.addStretch()
        self.setWidget(content)

        self._hands: deque[QFrame] = deque()
        self._hand_layout: QVBoxLayout | None = None
        self._lines: deque[str] = deque(maxlen=MAX_LINES)
        self.hero = ""
        """Your name: your actions stand out."""
        self._follow = True
        """Keep the latest line in view, unless the user scrolled up."""

        bar = self.verticalScrollBar()
        bar.rangeChanged.connect(self._on_range_changed)
        bar.valueChanged.connect(self._on_scrolled)

    # --- Reading -----------------------------------------------------------------

    def text(self) -> str:
        """The whole history as plain text, one line per entry."""
        return "\n".join(self._lines)

    @property
    def hand_count(self) -> int:
        return len(self._hands)

    # --- Writing -----------------------------------------------------------------

    def clear(self) -> None:
        while self._hands:
            self._remove(self._hands.popleft())

        self._hand_layout = None
        self._lines.clear()
        self._follow = True

    def start_hand(self, number: int, blinds: str, line: str | None = None) -> None:
        """A new block: the hand's number and its blinds (``line``: its plain
        text, when not the usual one)."""
        frame = QFrame()
        frame.setObjectName("historyHand")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(2)

        header = QHBoxLayout()
        header.addWidget(_label(f"Hand #{number}", "historyHandTitle"), stretch=1)
        header.addWidget(_label(blinds, "historyBlinds"))
        layout.addLayout(header)

        self._layout.insertWidget(self._layout.count() - 1, frame)
        self._hands.append(frame)
        self._hand_layout = layout

        while len(self._hands) > MAX_HANDS:
            self._remove(self._hands.popleft())

        self._lines.append(f"\n── Hand #{number} ──" if line is None else line)

    def add_section(
        self, title: str, cards: Sequence[Card] = (), line: str | None = None
    ) -> None:
        """A street (with the board so far) or your cards."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 6, 0, 2)
        row.setSpacing(3)
        row.addWidget(_label(title.upper(), "historySection"))
        row.addSpacing(4)

        for widget in _cards(cards):
            row.addWidget(widget)

        row.addStretch()
        self._add_row(row)

        if line is not None:
            self._lines.append(line)

    def add_action(
        self, event: ActionEvent, prefix: str = "", suffix: str = ""
    ) -> None:
        """One action: the player, then what they did, coloured by kind.

        ``prefix`` or ``suffix`` qualify it (an action decided by the clock).
        """
        description = describe_action(event)
        text = f"{prefix}{description}{suffix}"
        self._add_player_row(
            event.player, text[:1].upper() + text[1:], action_tone(event)
        )
        self._lines.append(
            f"{event.player} {prefix}{description}{suffix}"
            if prefix
            else f"{event.player}: {description}{suffix}"
        )

    def add_cards(
        self, player: str, cards: Sequence[Card], detail: str, line: str
    ) -> None:
        """A player's cards: shown at showdown, revealed after an all-in..."""
        row = QHBoxLayout()
        row.setSpacing(3)
        name = _label(player, "historyName")
        name.setFixedWidth(NAME_WIDTH)
        name.setProperty("hero", player == self.hero)
        row.addWidget(name)

        for widget in _cards(cards):
            row.addWidget(widget)

        if detail:
            row.addSpacing(4)
            label = _label(detail, "historyAction", Tone.PASSIVE)
            label.setWordWrap(True)
            row.addWidget(label, stretch=1)
        else:
            row.addStretch()

        self._add_row(row)
        self._lines.append(line)

    def add_note(self, text: str, tone: Tone = Tone.NOTE) -> None:
        """A result, an elimination, a rebuy..."""
        label = _label(text.strip(), "historyNote", tone)
        label.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(label)
        self._add_row(row)
        self._lines.append(text)

    # --- Inside ------------------------------------------------------------------

    def _add_player_row(self, player: str, text: str, tone: Tone) -> None:
        row = QHBoxLayout()
        row.setSpacing(6)
        name = _label(player, "historyName")
        name.setFixedWidth(NAME_WIDTH)
        name.setProperty("hero", player == self.hero)
        action = _label(text, "historyAction", tone)
        action.setWordWrap(True)
        row.addWidget(name)
        row.addWidget(action, stretch=1)
        self._add_row(row)

    def _add_row(self, row: QHBoxLayout) -> None:
        if self._hand_layout is None:  # Before the first hand (a Spin's draw).
            self._start_block()

        assert self._hand_layout is not None
        self._hand_layout.addLayout(row)

    def _start_block(self) -> None:
        """A block of its own for lines outside any hand."""
        frame = QFrame()
        frame.setObjectName("historyHand")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 8)
        self._layout.insertWidget(self._layout.count() - 1, frame)
        self._hands.append(frame)
        self._hand_layout = layout

    def _remove(self, frame: QFrame) -> None:
        if self._hand_layout is not None and frame.layout() is self._hand_layout:
            self._hand_layout = None

        frame.hide()
        frame.deleteLater()

    def _on_range_changed(self, _minimum: int, maximum: int) -> None:
        if self._follow:
            self.verticalScrollBar().setValue(maximum)

    def _on_scrolled(self, value: int) -> None:
        self._follow = value >= self.verticalScrollBar().maximum() - 4
