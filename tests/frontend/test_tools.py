"""The V1.1 tools: replayer, equity calculator, My stats and sessions."""

import json
from pathlib import Path

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from backend.application.game_modes import GameMode
from backend.application.hand_records import load_session_record
from backend.simulation.my_stats import compute_my_stats
from frontend.formatting import parse_cards
from frontend.ui.equity_screen import EquityScreen
from frontend.ui.main_window import MainWindow
from frontend.ui.replayer_screen import ReplayerScreen
from tests.session_files import (
    HUMAN,
    cash_session,
    downgrade_to_version_3,
    tournament_session,
)


@pytest.fixture
def sessions(tmp_path: Path) -> Path:
    """A folder with a cash game, a tournament and a Spin & Go."""
    folder = tmp_path / "sessions"
    folder.mkdir()
    cash_session(folder / "pk_sess_20261110_100000.dat", hands=8)
    tournament_session(folder / "pk_sess_20261111_100000.dat", seed=3)
    tournament_session(folder / "pk_sess_20261112_100000.dat", spin=True)

    return folder


def open_window(qapp: QApplication, folder: Path) -> MainWindow:
    window = MainWindow(save_sessions=False, session_dir=folder)
    window.main_menu.card("tools").click()
    assert window.current_screen is window.tools_screen

    return window


# --- Tools screen ----------------------------------------------------------------


def test_the_tools_screen_offers_four_tools(qapp: QApplication, tmp_path: Path) -> None:
    window = open_window(qapp, tmp_path)

    assert [card.mode.key for card in window.tools_screen.cards] == [
        "replayer",
        "equity",
        "my_stats",
        "sessions",
    ]
    assert all(card.isEnabled() for card in window.tools_screen.cards)

    window.tools_screen.back_button.click()
    assert window.current_screen is window.main_menu


def test_the_replayer_needs_a_saved_hand(qapp: QApplication, tmp_path: Path) -> None:
    window = open_window(qapp, tmp_path)

    window.tools_screen.card("replayer").click()

    assert window.current_screen is window.tools_screen
    assert "No saved hand yet" in window.tools_screen.message_label.text()


def test_the_replayer_opens_the_last_hand_of_the_latest_session(
    qapp: QApplication, sessions: Path
) -> None:
    window = open_window(qapp, sessions)

    window.tools_screen.card("replayer").click()

    replayer = window.replayer_screen
    assert window.current_screen is replayer
    assert replayer.session is not None
    assert replayer.session.mode == GameMode.SPIN, "the latest session"
    assert replayer.hand_index == len(replayer.session.hands) - 1
    assert replayer.step == 0

    replayer.back_button.click()
    assert window.current_screen is window.tools_screen


# --- Replayer ----------------------------------------------------------------------


def replayer_on(folder: Path, hand: int = 0) -> ReplayerScreen:
    session = load_session_record(next(folder.glob("pk_sess_20261110_*.dat")))
    replayer = ReplayerScreen()
    replayer.resize(1200, 760)
    replayer.show_hand(session, hand)

    return replayer


def test_the_replayer_steps_through_a_hand(qapp: QApplication, sessions: Path) -> None:
    replayer = replayer_on(sessions)
    replay = replayer.replay
    assert replay is not None and replayer.hand is not None
    record = replay.record
    first_lines = replayer.history_view.toPlainText().splitlines()

    assert first_lines[0].startswith(f"── Hand #{record.number}")
    assert f"Dealt to {HUMAN}" in first_lines[1]
    assert not replayer.previous_button.isEnabled()
    assert replayer.step_label.text() == f"Step 0 / {replay.step_count}"
    seats = {s.name: s for s in replayer.table_widget.state.seats}
    assert seats[HUMAN].cards_face_up, "your own cards"

    replayer.next_button.click()
    assert replayer.step == 1
    assert len(replayer.history_view.toPlainText().splitlines()) > len(first_lines)

    replayer.last_button.click()
    assert replayer.hand.finished
    assert not replayer.next_button.isEnabled()
    assert "wins" in replayer.history_view.toPlainText().splitlines()[-1]

    replayer.first_button.click()
    assert replayer.step == 0
    assert replayer.history_view.toPlainText().splitlines() == first_lines


def test_show_all_cards_turns_every_hand_face_up(
    qapp: QApplication, sessions: Path
) -> None:
    replayer = replayer_on(sessions)
    hidden = [s.cards_face_up for s in replayer.table_widget.state.seats]

    replayer.show_all_check.setChecked(True)

    shown = [s.cards_face_up for s in replayer.table_widget.state.seats]
    assert all(shown)
    assert not all(hidden), "the others' cards were face down"


def test_the_replayer_moves_between_hands(qapp: QApplication, sessions: Path) -> None:
    replayer = replayer_on(sessions, hand=0)
    session = replayer.session
    assert session is not None
    assert not replayer.previous_hand_button.isEnabled()

    replayer.next_hand_button.click()

    assert replayer.hand_index == 1
    assert replayer.replay is not None
    assert replayer.replay.record is session.hands[1]

    replayer.show_hand(session, len(session.hands) - 1)
    assert not replayer.next_hand_button.isEnabled()


def test_play_runs_the_hand_to_the_end(qapp: QApplication, sessions: Path) -> None:
    replayer = replayer_on(sessions)
    replayer.speed_combo.setCurrentIndex(replayer.speed_combo.findData("Turbo"))

    replayer.play_button.click()
    assert replayer.is_playing

    for _ in range(400):
        if not replayer.is_playing:
            break

        QTest.qWait(20)

    assert replayer.at_end and not replayer.is_playing
    assert replayer.play_button.text() == "Play"


def test_a_hand_saved_before_v1_1_shows_its_history_as_text(
    qapp: QApplication, tmp_path: Path
) -> None:
    path = cash_session(tmp_path / "old.dat", hands=3)
    downgrade_to_version_3(path)
    session = load_session_record(path)
    replayer = ReplayerScreen()

    replayer.show_hand(session, 1)

    assert replayer.replay is None
    assert replayer.view_stack.currentWidget() is replayer.message_label
    assert "saved before V1.1" in replayer.message_label.text()
    history = replayer.history_view.toPlainText()
    assert "posts small blind" in history and " wins " in history
    assert not replayer.play_button.isEnabled()
    assert not replayer.next_button.isEnabled()
    assert replayer.next_hand_button.isEnabled()


def test_the_replayer_follows_the_show_in_bb_setting(
    qapp: QApplication, sessions: Path
) -> None:
    window = open_window(qapp, sessions)
    window.tools_screen.card("replayer").click()

    window.replayer_screen.big_blinds_check.setChecked(True)

    assert window.game_screen.show_in_big_blinds
    assert window.profile.settings.show_in_big_blinds
    assert window.replayer_screen.table_widget.pot_label.text().endswith("BB")


# --- Session browser ---------------------------------------------------------------


def test_the_browser_lists_the_sessions_most_recent_first(
    qapp: QApplication, sessions: Path
) -> None:
    window = open_window(qapp, sessions)
    window.tools_screen.card("sessions").click()
    browser = window.session_browser_screen

    assert window.current_screen is browser
    assert [s.mode for s in browser.visible_sessions] == [
        GameMode.SPIN,
        GameMode.TOURNAMENT,
        GameMode.CASH,
    ]
    assert browser.sessions_table.rowCount() == 3
    assert browser.session is browser.visible_sessions[0]
    assert browser.notice_label.text() == ""


def test_the_browser_filters_by_mode_and_shows_a_session(
    qapp: QApplication, sessions: Path
) -> None:
    window = open_window(qapp, sessions)
    window.tools_screen.card("sessions").click()
    browser = window.session_browser_screen

    browser.filter_combo.setCurrentIndex(browser.filter_combo.findData(GameMode.CASH))

    assert len(browser.visible_sessions) == 1
    session = browser.session
    assert session is not None and session.mode == GameMode.CASH
    assert browser.hands_table.rowCount() == 8
    assert browser.chart.points[-1] == (8, (session.net_chips,))
    assert f"{HUMAN} against" in browser.summary_label.text()


def test_the_browser_opens_the_replayer_on_the_chosen_hand(
    qapp: QApplication, sessions: Path
) -> None:
    window = open_window(qapp, sessions)
    window.tools_screen.card("sessions").click()
    browser = window.session_browser_screen
    browser.filter_combo.setCurrentIndex(browser.filter_combo.findData(GameMode.CASH))

    browser.select_hand(4)
    browser.replay_button.click()

    assert window.current_screen is window.replayer_screen
    assert window.replayer_screen.hand_index == 4

    window.replayer_screen.back_button.click()
    assert window.current_screen is browser


def test_the_browser_reports_unreadable_files_and_opens_any_file(
    qapp: QApplication, sessions: Path, tmp_path: Path
) -> None:
    (sessions / "pk_sess_20261113_100000.dat").write_text("{", encoding="utf-8")
    elsewhere = cash_session(tmp_path / "elsewhere.dat", hands=2, seed=9)
    window = open_window(qapp, sessions)
    window.tools_screen.card("sessions").click()
    browser = window.session_browser_screen

    assert browser.notice_label.text() == "1 file could not be read."

    browser.open_file(elsewhere)

    assert browser.session is not None and browser.session.path == elsewhere
    assert len(browser.visible_sessions) == 4


def test_an_empty_folder_shows_an_empty_browser(
    qapp: QApplication, tmp_path: Path
) -> None:
    window = open_window(qapp, tmp_path)
    window.tools_screen.card("sessions").click()
    browser = window.session_browser_screen

    assert browser.sessions_table.rowCount() == 0
    assert "No saved session yet" in browser.summary_label.text()
    assert not browser.replay_button.isEnabled()


# --- My stats ----------------------------------------------------------------------


def test_my_stats_shows_the_stats_of_every_session(
    qapp: QApplication, sessions: Path
) -> None:
    window = open_window(qapp, sessions)
    window.tools_screen.card("my_stats").click()
    screen = window.my_stats_screen
    expected = compute_my_stats(window.library.scan().sessions)

    assert window.current_screen is screen
    assert screen.stats.hands == expected.hands > 0
    assert screen.summary_label.text() == f"3 sessions   ·   {expected.hands} hands"
    vpip = expected.tendencies.vpip
    assert vpip is not None
    assert screen.tendency("VPIP") == f"{vpip:.0%}"
    results = screen.results_label.text()
    assert "Cash games:" in results and "Tournaments: 1 played" in results
    assert "Spin & Go: 1 played" in results


def test_my_stats_filters_by_mode(qapp: QApplication, sessions: Path) -> None:
    window = open_window(qapp, sessions)
    window.tools_screen.card("my_stats").click()
    screen = window.my_stats_screen

    screen.filter_combo.setCurrentIndex(screen.filter_combo.findData(GameMode.CASH))

    assert screen.stats.sessions == 1
    assert screen.positions_table.rowCount() > 0
    assert "Tournaments: none yet." in screen.results_label.text()


def test_my_stats_without_any_session(qapp: QApplication, tmp_path: Path) -> None:
    window = open_window(qapp, tmp_path)
    window.tools_screen.card("my_stats").click()
    screen = window.my_stats_screen

    assert "No hand played yet" in screen.summary_label.text()
    assert screen.tendency("VPIP") == "—"
    assert screen.positions_table.rowCount() == 0


# --- Equity calculator -------------------------------------------------------------


def test_equity_on_the_flop_is_exact(qapp: QApplication) -> None:
    screen = EquityScreen()
    screen.set_hands(["Ah Ad", "Kc Ks"], "2c 7d 9h")

    screen.calculate()
    screen.run_to_end()

    assert screen.status_label.text() == "Exact: 990 of 990 boards counted"
    aces, kings = screen.rows
    assert aces.equity_label.text() == "91.6%"
    assert kings.equity_label.text() == "8.4%"
    assert screen.calculate_button.isEnabled() and not screen.stop_button.isEnabled()


def test_equity_against_a_random_hand_is_estimated(qapp: QApplication) -> None:
    screen = EquityScreen()
    screen.seed = 4
    screen.set_hands(["A♠ A♦", ""])

    screen.calculate()
    assert screen.is_running and screen.stop_button.isEnabled()
    screen.run_to_end()

    assert screen.status_label.text().startswith("Estimate: 60 000 random boards")
    equity = float(screen.rows[0].equity_label.text().split("%")[0])
    assert equity == pytest.approx(85.2, abs=1.5)
    assert "±" in screen.rows[0].equity_label.text()


def test_the_equity_screen_runs_on_the_event_loop(qapp: QApplication) -> None:
    screen = EquityScreen()
    screen.seed = 1
    screen.set_hands(["", "", ""])

    screen.calculate()
    QTest.qWait(60)

    assert screen.calculator is not None and screen.calculator.boards > 0
    screen.stop()
    assert not screen.is_running


@pytest.mark.parametrize(
    ("hands", "board", "message"),
    [
        (["Ah Ad", "Ah Kd"], "", "twice"),
        (["Ah", "Kc Ks"], "", "Hand 1: two cards"),
        (["Ah Ad", "Kc Ks"], "2c 3c 4c 5c 6c 7c", "at most five"),
        (["Zz Ad", "Kc Ks"], "", "not a card"),
    ],
)
def test_wrong_cards_are_explained(
    qapp: QApplication, hands: list[str], board: str, message: str
) -> None:
    screen = EquityScreen()
    screen.set_hands(hands, board)

    screen.calculate()

    assert message in screen.error_label.text()
    assert not screen.is_running


def test_hands_can_be_added_and_removed(qapp: QApplication) -> None:
    screen = EquityScreen()
    assert len(screen.rows) == 2
    assert not screen.rows[0].remove_button.isEnabled()

    for _ in range(6):
        screen.add_button.click()

    assert len(screen.rows) == 6
    assert not screen.add_button.isEnabled()

    screen.rows[2].remove_button.click()
    assert len(screen.rows) == 5
    assert [row.label.text() for row in screen.rows][-1] == "Hand 5"


def test_typing_makes_the_results_stale(qapp: QApplication) -> None:
    screen = EquityScreen()
    screen.set_hands(["Ah Ad", "Kc Ks"], "2c 7d 9h")
    screen.calculate()
    screen.run_to_end()

    screen.board_edit.setText("2c 7d 9h Qs")

    assert screen.rows[0].equity_label.text() == "—"
    assert screen.status_label.text() == ""
    assert [w.card for w in screen.board_preview.card_widgets][:4] == [
        "2C",
        "7D",
        "9H",
        "QS",
    ]


@pytest.mark.parametrize(
    ("text", "cards"),
    [
        ("AsKd", ("AS", "KD")),
        ("as kd", ("AS", "KD")),
        ("A♠ K♦", ("AS", "KD")),
        ("10h, 9h", ("TH", "9H")),
        ("", ()),
    ],
)
def test_cards_are_read_in_every_usual_spelling(
    text: str, cards: tuple[str, ...]
) -> None:
    assert parse_cards(text) == cards


@pytest.mark.parametrize("text", ["A", "Ax", "1s", "AsAs"])
def test_unreadable_cards_are_refused(text: str) -> None:
    with pytest.raises(ValueError):
        parse_cards(text)


# --- Saving the games the tools read ----------------------------------------------


def test_a_game_played_is_saved_where_the_tools_read(
    qapp: QApplication, tmp_path: Path
) -> None:
    window = MainWindow(session_dir=tmp_path)
    window.game_screen.step_delay_ms = 0
    window.main_menu.card("cash").click()
    window.cash_setup_screen.play_button.click()
    game = window.game_screen.game
    assert game is not None

    while game.is_hand_in_progress:
        if game.is_waiting_for_human:
            window.game_screen.action_panel.fold_button.click()
        else:
            window.game_screen._play_step()  # noqa: SLF001 - the bots, at once

    saved = list(tmp_path.glob("*.dat"))
    assert len(saved) == 1
    data = json.loads(saved[0].read_text(encoding="utf-8"))
    assert (data["human"], data["mode"]) == ("Hero", "cash")
    window.game_screen.stop()
    window.back_to_menu()

    window.main_menu.card("tools").click()
    window.tools_screen.card("replayer").click()

    assert window.current_screen is window.replayer_screen
    assert window.replayer_screen.replay is not None
