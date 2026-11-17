"""The hand history (V1.4): blocks per hand, cards drawn, coloured actions,
and a button to show or hide it."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from backend.application.hand_records import load_session_record
from backend.application.profile import ProfileStore
from backend.poker_engine.constants import ActionType, Street
from backend.poker_engine.models import ActionEvent
from backend.simulation.config import SeatSpec, SimulationConfig
from frontend.components.card_widget import CardWidget
from frontend.components.hand_history import (
    MAX_HANDS,
    HandHistoryView,
    Tone,
    action_tone,
)
from frontend.ui.arena_watch_screen import ArenaWatchScreen
from frontend.ui.game_screen import GameScreen
from frontend.ui.main_window import MainWindow
from frontend.ui.replayer_screen import ReplayerScreen
from tests.frontend.test_game_screen import HUMAN, make_game
from tests.frontend.windows import ProcessUntil, open_table
from tests.session_files import cash_session


def event(player: str, action: str, amount: int = 0, initiator: bool = False):
    return ActionEvent(
        sequence=0,
        street=Street.PREFLOP,
        player=player,
        position=None,
        action=action,
        amount=amount,
        bet_before=0,
        bet_after=amount,
        pot_after=0,
        current_bet_after=amount,
        bet_initiator=initiator,
    )


def labels(view: HandHistoryView, name: str) -> list[QLabel]:
    return [label for label in view.findChildren(QLabel) if label.objectName() == name]


def shown_cards(view: HandHistoryView) -> list[str | None]:
    return [card.card for card in view.findChildren(CardWidget)]


# --- What a hand looks like ------------------------------------------------------


def test_each_action_is_coloured_by_kind() -> None:
    assert action_tone(event("A", "post_sb", 5)) == Tone.POST
    assert action_tone(event("A", ActionType.FOLD)) == Tone.FOLD
    assert action_tone(event("A", ActionType.CHECK)) == Tone.PASSIVE
    assert action_tone(event("A", ActionType.CALL, 10)) == Tone.PASSIVE
    assert action_tone(event("A", ActionType.RAISE, 40)) == Tone.AGGRESSIVE
    assert action_tone(event("A", ActionType.ALL_IN, 900)) == Tone.ALL_IN


def test_a_hand_is_a_block_with_its_cards_drawn(qapp: QApplication) -> None:
    view = HandHistoryView()
    view.hero = "Hero"
    view.start_hand(7, "5/10")
    view.add_action(event("Alex", "post_sb", 5))
    view.add_section("Your cards", ("QH", "5C"), line="Your cards: Q♥ 5♣")
    view.add_action(event("Hero", ActionType.RAISE, 30))
    view.add_section("Flop", ("2S", "2D", "9C"), line="*** FLOP *** 2♠ 2♦ 9♣")
    view.add_cards("Alex", ("AS", "KD"), "folded", line="Alex had A♠ K♦ (folded)")
    view.add_note("Hero wins 45", Tone.RESULT)

    assert view.hand_count == 1
    assert [label.text() for label in labels(view, "historyHandTitle")] == ["Hand #7"]
    assert [label.text() for label in labels(view, "historySection")] == [
        "YOUR CARDS",
        "FLOP",
    ]
    assert shown_cards(view) == ["QH", "5C", "2S", "2D", "9C", "AS", "KD"]

    actions = labels(view, "historyAction")
    assert actions[1].text() == "Raises to 30"
    assert actions[1].property("tone") == "aggressive"
    heroes = [
        label.text() for label in labels(view, "historyName") if label.property("hero")
    ]
    assert heroes == ["Hero"]

    assert view.text().splitlines() == [
        "",
        "── Hand #7 ──",
        "Alex: posts small blind 5",
        "Your cards: Q♥ 5♣",
        "Hero: raises to 30",
        "*** FLOP *** 2♠ 2♦ 9♣",
        "Alex had A♠ K♦ (folded)",
        "Hero wins 45",
    ]


def test_old_hands_leave_the_view(qapp: QApplication) -> None:
    view = HandHistoryView()

    for number in range(MAX_HANDS + 5):
        view.start_hand(number, "5/10")

    assert view.hand_count == MAX_HANDS
    assert "Hand #0 ──" in view.text(), "the text keeps them"

    view.clear()
    assert view.hand_count == 0 and view.text() == ""


def test_a_played_hand_fills_the_history(
    qapp: QApplication, process_until: ProcessUntil
) -> None:
    screen = GameScreen()
    screen.step_delay_ms = 0
    game = make_game(dealer_index=0)
    screen.start_game(game, human_name=HUMAN)
    process_until(lambda: game.is_waiting_for_human)

    hero = next(p for p in game.session.players if p.name == HUMAN)
    view = screen.history_view
    assert view.hand_count == 1
    assert shown_cards(view)[:2] == list(hero.hand)
    assert [label.text() for label in labels(view, "historySection")] == [
        "YOUR CARDS",
        "PRE-FLOP",
    ]
    screen.stop()


# --- Showing and hiding it --------------------------------------------------------


@pytest.fixture
def window(qapp: QApplication, tmp_path: Path) -> Iterator[MainWindow]:
    window = MainWindow(save_sessions=False, profile=ProfileStore(tmp_path / "p.json"))
    yield window
    window.close()


def test_the_button_hides_the_history_at_every_table_and_remembers_it(
    window: MainWindow,
) -> None:
    first, second = open_table(window, "cash"), open_table(window, "tournament")
    for table in (first, second):
        table.push(table.table_screen)
        table.resize(1200, 760)

    screen = first.table_screen
    assert screen.history_panel.isVisible()
    assert screen.history_button.isChecked()

    screen.history_button.click()

    assert not screen.history_panel.isVisible()
    assert not screen.history_button.isChecked()
    assert not second.table_screen.history_panel.isVisible()
    assert ProfileStore(window.profile.path).settings.show_history is False
    assert not open_table(window, "spin").table_screen.history_button.isChecked()

    window.open_settings().history_check.setChecked(True)
    assert screen.history_panel.isVisible()


def test_a_narrow_window_has_no_room_for_the_history(
    window: MainWindow, qapp: QApplication
) -> None:
    table = open_table(window, "cash")
    table.push(table.table_screen)
    screen = table.table_screen
    needed = screen.history_min_width
    assert 1000 < needed < 1200, "the table's controls need about 800 pixels"
    table.resize(needed - 40, 600)
    qapp.processEvents()

    assert not screen.history_panel.isVisible()
    assert not screen.history_button.isEnabled()

    table.resize(needed + 40, 700)
    qapp.processEvents()
    assert screen.history_panel.isVisible()


# --- The replayer and the Bot Arena -----------------------------------------------


def test_the_bot_arena_draws_every_bots_cards(qapp: QApplication) -> None:
    watch = ArenaWatchScreen()
    watch.start(
        SimulationConfig(seats=(SeatSpec("tag"), SeatSpec("lag")), hands=3, seed=4)
    )
    watch.toggle_pause()

    while not watch.is_complete:
        watch.step()

    view = watch.history_view
    assert view.hand_count == 4, "the seed line, then three hands"
    hole_cards = [label for label in labels(view, "historySection")]
    assert sum(label.text() == "HOLE CARDS" for label in hole_cards) == 3
    assert len(shown_cards(view)) >= 3 * 2, "both bots' cards, every hand"
    assert "All hands have been played." in view.text()
    watch.stop()


def test_the_replayer_draws_the_history_step_by_step(
    qapp: QApplication, tmp_path: Path
) -> None:
    cash_session(tmp_path / "pk_sess_20261110_100000.dat", hands=4)
    session = load_session_record(tmp_path / "pk_sess_20261110_100000.dat")
    replayer = ReplayerScreen()
    replayer.show_hand(session, 1)
    replay = replayer.replay
    assert replay is not None
    view = replayer.history_view
    dealt = view.text()

    assert view.hand_count == 1
    assert labels(view, "historySection")[0].text() == "YOUR CARDS"
    cards = replay.record.hole_cards(session.human)
    assert cards is not None and shown_cards(view)[:2] == list(cards)

    replayer.go_to(replay.step_count)  # Forward: only the new steps are added.
    full = view.text()
    assert full.startswith(dealt) and len(full) > len(dealt)
    assert view.hand_count == 1

    replayer.go_to(0)  # Back: written again from the deal.
    assert view.text() == dealt

    replayer.go_to(replay.step_count)
    assert view.text() == full
    replayer.stop()
