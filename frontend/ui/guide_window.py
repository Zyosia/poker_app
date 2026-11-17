"""The Guide: the application, its modes, the bot styles and the poker terms.

One window for the whole application (``open_guide``), opened from the main
menu and from the **?** buttons next to the play styles. A list of sections
on the left, the selected page on the right.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.bots.factory import BOT_TYPES
from frontend.guide import (
    ARENA_MEASURE_NOTE,
    ARENA_MEASURES,
    BOT_GUIDES,
    MAX_LEVEL,
    SECTIONS,
    TRAITS,
    Section,
)

WINDOW_SIZE = (900, 640)
NAVIGATION_WIDTH = 180
BOT_COLUMNS = 2
DOT = "●"
EMPTY_COLOR = "#3a4352"


def paragraph(text: str, object_name: str = "guideText") -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)

    return label


def meter(level: int) -> str:
    """``level`` dots out of five: the empty ones are dimmed."""
    empty = DOT * (MAX_LEVEL - level)

    return f'{DOT * level}<span style="color: {EMPTY_COLOR}">{empty}</span>'


class BotCard(QFrame):
    """One play style: what it does, its meters and how to beat it."""

    def __init__(self, key: str) -> None:
        super().__init__()
        self.setObjectName("guideCard")
        guide = BOT_GUIDES[key]
        self.key = key

        name = QLabel(BOT_TYPES[key].label)
        name.setObjectName("guideCardName")
        nickname = QLabel(guide.nickname)
        nickname.setObjectName("hintText")

        meters = QGridLayout()
        meters.setHorizontalSpacing(12)
        meters.setVerticalSpacing(2)

        for row, (trait, level) in enumerate(zip(TRAITS, guide.traits, strict=True)):
            meters.addWidget(QLabel(trait), row, 0)
            dots = QLabel(meter(level))
            dots.setObjectName("guideMeter")
            dots.setTextFormat(Qt.TextFormat.RichText)
            dots.setToolTip(f"{level} / {MAX_LEVEL}")
            meters.addWidget(dots, row, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        layout.addWidget(name)
        layout.addWidget(nickname)
        layout.addWidget(paragraph(guide.portrait))
        layout.addLayout(meters)

        measures = ARENA_MEASURES.get(key)

        if measures is not None:
            vpip, pfr, aggression = measures
            layout.addWidget(
                paragraph(
                    f"In the Bot Arena: VPIP {vpip:.0f}%, PFR {pfr:.0f}%, "
                    f"AF {aggression:.1f}",
                    "hintText",
                )
            )

        layout.addWidget(paragraph(f"<b>How to beat it:</b> {guide.how_to_beat}"))
        layout.addStretch()


class GuidePage(QScrollArea):
    """A section: its title, introduction and topics (or the bot cards)."""

    def __init__(self, section: Section) -> None:
        super().__init__()
        self.section = section
        self.setObjectName("guidePage")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setObjectName("guidePageContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(10)

        title = QLabel(section.title)
        title.setObjectName("guideTitle")
        layout.addWidget(title)
        layout.addWidget(paragraph(section.intro))

        for topic in section.topics:
            heading = QLabel(topic.title)
            heading.setObjectName("guideHeading")
            layout.addSpacing(6)
            layout.addWidget(heading)

            for text in topic.paragraphs:
                layout.addWidget(paragraph(text))

        self.bot_cards: list[BotCard] = []

        if section.key == "bots":
            layout.addLayout(self._bot_grid())

            if ARENA_MEASURE_NOTE:
                layout.addWidget(paragraph(ARENA_MEASURE_NOTE, "hintText"))

        layout.addStretch()
        self.setWidget(content)

    def _bot_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(12)

        for index, key in enumerate(BOT_TYPES):
            card = BotCard(key)
            self.bot_cards.append(card)
            grid.addWidget(card, index // BOT_COLUMNS, index % BOT_COLUMNS)

        return grid

    def show_bot(self, key: str) -> None:
        card = next((c for c in self.bot_cards if c.key == key), None)

        if card is not None:
            self.ensureWidgetVisible(card)


class GuideWindow(QWidget):
    """The guide, one page per section."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Guide · Poker")
        self.resize(*WINDOW_SIZE)
        self.setObjectName("guideWindow")

        self.navigation = QListWidget()
        self.navigation.setObjectName("guideNavigation")
        self.navigation.setFixedWidth(NAVIGATION_WIDTH)
        self.pages = QStackedWidget()
        self.page_by_key: dict[str, GuidePage] = {}

        for section in SECTIONS:
            self.navigation.addItem(section.title)
            page = GuidePage(section)
            self.page_by_key[section.key] = page
            self.pages.addWidget(page)

        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.navigation)
        layout.addWidget(self.pages, stretch=1)

    @property
    def current_section(self) -> str:
        page = self.pages.currentWidget()
        assert isinstance(page, GuidePage)

        return page.section.key

    def show_section(self, key: str, bot: str | None = None) -> None:
        """Show the page of ``key``; on the bot styles, scroll to ``bot``."""
        page = self.page_by_key[key]
        self.navigation.setCurrentRow(self.pages.indexOf(page))

        if bot is not None:
            page.show_bot(bot)


_window: GuideWindow | None = None


def open_guide(section: str = "welcome", bot: str | None = None) -> GuideWindow:
    """Show the guide (one window for the whole application) at ``section``."""
    global _window

    if _window is None:
        _window = GuideWindow()

    _window.show_section(section, bot)
    _window.show()
    _window.raise_()
    _window.activateWindow()

    return _window


def close_guide() -> None:
    """Close and forget the guide window (the application quits, tests)."""
    global _window

    if _window is not None:
        _window.close()
        _window.deleteLater()
        _window = None
