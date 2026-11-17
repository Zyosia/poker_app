"""Main window, the lobby: the main menu, Bot Arena, the tools and the bankroll.

Each Cash Game, Tournament and Spin & Go opens in a window of its own
(``GameWindow``), so several games are played at once, as in the rooms
online (multi-tabling). The lobby lists the open tables, arranges them, and
brings the table waiting for your decision to the front; when you act
there, the next table waiting for you comes forward.

The settings open from every window, in their own small window, with the
⚙ button at the top left.
"""

import math
import random
from pathlib import Path

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

from backend.application.bankroll import GameAccount, GameMode
from backend.application.hand_records import SessionLibrary, SessionRecord
from backend.application.persistence import SESSION_DIR, new_session_file_path
from backend.application.profile import MAX_VOLUME, ProfileStore, UserSettings
from backend.simulation.config import SimulationConfig
from backend.simulation.result import SimulationResult
from backend.simulation.tournament_runner import (
    TournamentRunConfig,
    TournamentRunResult,
)
from frontend.components.card_widget import CardWidget
from frontend.modes import MODES, TOOLS, Mode, ScreenKey
from frontend.sounds import SoundPlayer

from .arena_progress_screen import ArenaProgressScreen
from .arena_results_screen import ArenaResultsScreen
from .arena_setup_screen import ArenaSetupScreen
from .arena_watch_screen import ArenaWatchScreen
from .bankroll_screen import BankrollScreen
from .equity_screen import EquityScreen
from .game_window import WINDOW_SIZE, GameWindow
from .main_menu_screen import MainMenuScreen
from .my_stats_screen import MyStatsScreen
from .navigation_window import NavigationWindow
from .replayer_screen import ReplayerScreen
from .session_browser_screen import SessionBrowserScreen
from .settings_dialog import SettingsDialog
from .tools_screen import ToolsScreen

GAME_WINDOW_MODES = {
    ScreenKey.CASH_SETUP: GameMode.CASH,
    ScreenKey.TOURNAMENT_SETUP: GameMode.TOURNAMENT,
    ScreenKey.SPIN_SETUP: GameMode.SPIN,
}
"""The modes played in a window of their own."""
DIALOG_SETTINGS = (
    "sound_effects",
    "sound_volume",
    "turn_alert",
    "bot_cards",
    "table_speed",
    "auto_next_hand",
    "show_in_big_blinds",
    "four_color_deck",
    "bankroll_hints",
    "table_to_front",
)
"""What Restore defaults resets: the settings window, but not your name."""
CASCADE_STEP = 32
"""Pixels between two tables arranged in cascade."""


class MainWindow(NavigationWindow):
    """Top-level window of the application: the lobby."""

    def __init__(
        self,
        save_sessions: bool = True,
        parent: QWidget | None = None,
        rng: random.Random | None = None,
        profile: ProfileStore | None = None,
        session_dir: Path = SESSION_DIR,
        sounds: SoundPlayer | None = None,
    ) -> None:
        """``rng`` draws the tournaments' cards and bots (seeded in tests).

        ``profile`` holds the user's settings; without one they are kept in
        memory only, so tests never touch the user's real profile. Games are
        saved in ``session_dir``, where the tools read them back. ``sounds``
        plays the sound effects; without one nothing is heard (tests).
        """
        super().__init__(parent)
        self.setWindowTitle("Poker — No Limit Texas Hold'em")
        self.resize(1280, 800)
        self.setMinimumSize(1100, 700)

        self._save_sessions = save_sessions
        self.session_dir = session_dir
        self.library = SessionLibrary(session_dir)
        self._rng = rng or random.Random()
        self.profile = profile or ProfileStore()
        self.sounds = sounds or SoundPlayer()
        self.sounds.setParent(self)
        self.settings_dialog: SettingsDialog | None = None
        self._paused_for_settings: list[QWidget] = []
        """The tables paused while the settings are open, to restart after."""
        self.game_windows: list[GameWindow] = []
        """The open games, in the order they were opened."""
        self.waiting_tables: list[GameWindow] = []
        """The tables waiting for your decision, the longest waiting first."""

        self.main_menu = MainMenuScreen(MODES)
        self.arena_setup_screen = ArenaSetupScreen()
        self.arena_progress_screen = ArenaProgressScreen()
        self.arena_results_screen = ArenaResultsScreen()
        self.arena_watch_screen = ArenaWatchScreen()
        self.bankroll_screen = BankrollScreen()
        self.tools_screen = ToolsScreen(TOOLS)
        self.replayer_screen = ReplayerScreen()
        self.equity_screen = EquityScreen()
        self.my_stats_screen = MyStatsScreen()
        self.session_browser_screen = SessionBrowserScreen(self.library)

        recovered = self.profile.bankroll.recover_open_games()
        self.startup_notice: str | None = None
        """Told to the user at launch: the games the last run did not settle."""

        if recovered:
            self.profile.save()
            self.startup_notice = "\n".join(
                f"{t.description} ({t.amount:+,}).".replace(",", " ") for t in recovered
            )

        self.mode_screens: dict[ScreenKey, QWidget] = {
            ScreenKey.ARENA_SETUP: self.arena_setup_screen,
            ScreenKey.TOOLS: self.tools_screen,
        }

        self.add_screens(
            self.main_menu,
            self.arena_setup_screen,
            self.arena_progress_screen,
            self.arena_results_screen,
            self.arena_watch_screen,
            self.bankroll_screen,
            self.tools_screen,
            self.replayer_screen,
            self.equity_screen,
            self.my_stats_screen,
            self.session_browser_screen,
        )
        self.show_first(self.main_menu)
        self.settings_requested.connect(self.open_settings)

        self.table_screens = (self.arena_watch_screen, self.replayer_screen)
        """The tables of the lobby (watched, not played): amounts in BB."""

        for screen in self.table_screens:
            screen.show_in_big_blinds_changed.connect(self.set_show_in_big_blinds)

        self.main_menu.mode_selected.connect(self.open_mode)
        self.main_menu.quit_requested.connect(self.close)
        self.main_menu.bankroll_bar.bankroll_requested.connect(self.open_bankroll)
        self.main_menu.bankroll_bar.reload_requested.connect(self.reload_bankroll)
        self.main_menu.tables_panel.table_selected.connect(
            lambda index: self.bring_to_front(self.game_windows[index])
        )
        self.main_menu.tables_panel.tile_requested.connect(self.tile_tables)
        self.main_menu.tables_panel.cascade_requested.connect(self.cascade_tables)

        self.bankroll_screen.back_requested.connect(self.back)
        self.bankroll_screen.changed.connect(
            lambda: self.on_bankroll_screen_changed(self.bankroll_screen)
        )
        self.apply_settings()

        self.arena_setup_screen.run_requested.connect(self.run_arena)
        self.arena_setup_screen.watch_requested.connect(self.watch_arena)
        self.arena_setup_screen.back_requested.connect(self.back)
        self.arena_progress_screen.finished.connect(self.show_arena_result)
        self.arena_progress_screen.cancelled.connect(self.back)
        self.arena_results_screen.back_requested.connect(self.back)
        self.arena_results_screen.rerun_requested.connect(self.rerun_arena)
        self.arena_watch_screen.back_requested.connect(self.back)

        self.tools_screen.tool_selected.connect(self.open_tool)
        self.tools_screen.back_requested.connect(self.back)
        self.replayer_screen.back_requested.connect(self.back)
        self.equity_screen.back_requested.connect(self.back)
        self.my_stats_screen.back_requested.connect(self.back)
        self.my_stats_screen.refresh_requested.connect(self._show_my_stats)
        self.session_browser_screen.back_requested.connect(self.back)
        self.session_browser_screen.replay_requested.connect(self.replay_hand)

    # --- Settings ------------------------------------------------------------

    def apply_settings(self) -> None:
        """Show every window as the user's settings say."""
        settings = self.profile.settings
        self.sounds.enabled = settings.sound_effects
        self.sounds.set_volume(settings.sound_volume / MAX_VOLUME)

        for screen in self.table_screens:
            screen.set_show_in_big_blinds(settings.show_in_big_blinds)

        for window in self.game_windows:
            window.apply_settings(settings)

        if CardWidget.four_colors != settings.four_color_deck:
            CardWidget.four_colors = settings.four_color_deck

            for window in (self, *self.game_windows):
                window.update()  # Every card is painted again.

        self.refresh_bankroll()

    def open_settings(self, parent: QWidget | None = None) -> SettingsDialog:
        """Open the settings over ``parent`` (the lobby by default); the
        tables running are paused meanwhile, and go on once they close."""
        if self.settings_dialog is not None:
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return self.settings_dialog

        self._paused_for_settings = []

        for window in self.game_windows:
            table = window.table_to_pause()

            if table is not None:
                table.toggle_pause()
                self._paused_for_settings.append(table)

        dialog = SettingsDialog(self.profile.settings, self.sounds, parent or self)
        dialog.setting_changed.connect(self._on_setting_changed)
        dialog.defaults_requested.connect(self.restore_default_settings)
        dialog.finished.connect(self._on_settings_closed)
        self.settings_dialog = dialog
        dialog.open()

        return dialog

    def _on_setting_changed(self, name: str, value: object) -> None:
        self.save_setting(name, value)
        self.apply_settings()

    def restore_default_settings(self) -> None:
        defaults = UserSettings()

        for name in DIALOG_SETTINGS:
            setattr(self.profile.settings, name, getattr(defaults, name))

        self.profile.save()
        self.apply_settings()

        if self.settings_dialog is not None:
            self.settings_dialog.show_settings(self.profile.settings)

    def _on_settings_closed(self) -> None:
        dialog = self.settings_dialog
        self.settings_dialog = None
        paused, self._paused_for_settings = self._paused_for_settings, []

        if dialog is not None:
            dialog.deleteLater()

        for window in self.game_windows:
            table = window.table_screen

            if table in paused and table.game is not None and table.paused:
                table.toggle_pause()

    def set_show_in_big_blinds(self, enabled: bool) -> None:
        """Show amounts in big blinds on every table, and remember it."""
        for screen in self.table_screens:
            screen.set_show_in_big_blinds(enabled)

        for window in self.game_windows:
            window.table_screen.set_show_in_big_blinds(enabled)

        self.save_setting("show_in_big_blinds", enabled)

    def set_table_speed(self, name: str) -> None:
        for window in self.game_windows:
            window.table_screen.set_speed(name)

        self.save_setting("table_speed", name)

    def set_auto_next_hand(self, enabled: bool) -> None:
        for window in self.game_windows:
            window.table_screen.set_auto_next_hand(enabled)

        self.save_setting("auto_next_hand", enabled)

    def save_setting(self, name: str, value: object) -> None:
        setattr(self.profile.settings, name, value)
        self.profile.save()

    # --- What the game windows share ------------------------------------------

    def new_save_path(self) -> Path | None:
        if not self._save_sessions:
            return None

        return new_session_file_path(self.session_dir)

    def new_rng(self) -> random.Random:
        """A generator of its own for a tournament (seeded by the lobby's)."""
        return random.Random(self._rng.getrandbits(64))

    def new_account(self, mode: GameMode, description: str) -> GameAccount:
        return GameAccount(
            self.profile.bankroll, mode, description, save=self.save_bankroll
        )

    # --- Bankroll ------------------------------------------------------------

    def refresh_bankroll(self) -> None:
        """Show the balance on the menu and in every game window."""
        bankroll = self.profile.bankroll
        self.main_menu.bankroll_bar.set_balance(bankroll.balance, bankroll.can_reload)

        if self.history and self.current_screen is self.bankroll_screen:
            self.bankroll_screen.refresh()

        for window in self.game_windows:
            window.refresh_bankroll()

    def save_bankroll(self) -> None:
        self.profile.save()
        self.refresh_bankroll()

    def open_bankroll(self) -> None:
        self.bankroll_screen.show_bankroll(
            self.profile.bankroll, self.profile.settings.bankroll_hints
        )
        self.push(self.bankroll_screen)

    def reload_bankroll(self) -> None:
        if self.profile.bankroll.can_reload:
            self.profile.bankroll.reload()
            self.save_bankroll()

    def on_bankroll_screen_changed(self, screen: BankrollScreen) -> None:
        self.profile.settings.bankroll_hints = screen.hints_enabled
        self.save_bankroll()

    # --- Game windows (multi-tabling) ----------------------------------------------

    def open_mode(self, mode: Mode) -> None:
        if mode.screen is None:
            return

        if mode.screen in GAME_WINDOW_MODES:
            self.open_game_window(GAME_WINDOW_MODES[mode.screen])
        else:
            self.push(self.mode_screens[mode.screen])

    def open_game_window(self, mode: GameMode) -> GameWindow:
        """A new window for a game of ``mode``, starting at its setup screen."""
        taken = {window.number for window in self.game_windows}
        number = next(n for n in range(1, len(taken) + 2) if n not in taken)
        window = GameWindow(mode, self, number)
        window.settings_requested.connect(lambda: self.open_settings(window))
        window.your_turn_changed.connect(self._on_your_turn_changed)
        window.closed.connect(self._on_game_window_closed)
        self.game_windows.append(window)

        area = self._screen_area()
        window.resize(
            min(WINDOW_SIZE[0], area.width()), min(WINDOW_SIZE[1], area.height())
        )
        offset = CASCADE_STEP * (1 + (number - 1) % 8)
        window.move(self.pos() + QPoint(offset, offset))
        window.show()
        self.bring_to_front(window)
        self._refresh_tables_panel()

        return window

    def _on_game_window_closed(self, window: GameWindow) -> None:
        if window in self.game_windows:
            self.game_windows.remove(window)

        if window in self.waiting_tables:
            self.waiting_tables.remove(window)

        dialog = self.settings_dialog

        if dialog is not None and dialog.parent() is window:
            dialog.close()

        self.refresh_bankroll()
        self._refresh_tables_panel()

    def _on_your_turn_changed(self, window: GameWindow, waiting: bool) -> None:
        """The table waiting for you comes to the front, unless you are
        deciding at another table; once you acted, the next one comes."""
        if waiting:
            if window not in self.waiting_tables:
                self.waiting_tables.append(window)

            QApplication.alert(window)

            if self._may_bring_forward(window):
                self.bring_to_front(window)
        elif window in self.waiting_tables:
            self.waiting_tables.remove(window)
            active = QApplication.activeWindow()

            if (
                self.waiting_tables
                and active in (window, None)
                and self._may_bring_forward(self.waiting_tables[0])
            ):
                self.bring_to_front(self.waiting_tables[0])

        self._refresh_tables_panel()

    def _may_bring_forward(self, window: GameWindow) -> bool:
        if not self.profile.settings.table_to_front or self.settings_dialog:
            return False

        active = QApplication.activeWindow()

        return not (
            isinstance(active, GameWindow) and active is not window and active.your_turn
        )

    def bring_to_front(self, window: GameWindow) -> None:
        if window.isMinimized():
            window.showNormal()

        window.raise_()
        window.activateWindow()

    def _refresh_tables_panel(self) -> None:
        self.main_menu.tables_panel.show_tables(
            [(window.title, window.your_turn) for window in self.game_windows]
        )

    def tile_tables(self) -> None:
        """Arrange the tables side by side, filling the screen."""
        windows = self.game_windows

        if not windows:
            return

        area = self._screen_area()
        columns = math.ceil(math.sqrt(len(windows)))
        rows = math.ceil(len(windows) / columns)
        width = area.width() // columns
        height = area.height() // rows

        for index, window in enumerate(windows):
            window.showNormal()
            frame = window.frameGeometry().size() - window.geometry().size()
            window.resize(width - frame.width(), height - frame.height())
            window.move(
                area.left() + index % columns * width,
                area.top() + index // columns * height,
            )
            window.raise_()

    def cascade_tables(self) -> None:
        """Stack the tables, each a little lower and to the right."""
        area = self._screen_area()
        width = min(WINDOW_SIZE[0], area.width())
        height = min(WINDOW_SIZE[1], area.height())

        for index, window in enumerate(self.game_windows):
            window.showNormal()
            window.resize(width, height)
            step = CASCADE_STEP * (index % 10)
            window.move(area.left() + step, area.top() + step)
            window.raise_()

    def _screen_area(self) -> QRect:
        screen = self.screen() or QGuiApplication.primaryScreen()

        return screen.availableGeometry()

    # --- Navigation ----------------------------------------------------------

    def stop_screen(self, screen: QWidget) -> None:
        if screen is self.arena_watch_screen:
            self.arena_watch_screen.stop()
        elif screen is self.replayer_screen:
            self.replayer_screen.stop()
        elif screen is self.equity_screen:
            self.equity_screen.stop()

    # --- Tools ----------------------------------------------------------------

    def open_tool(self, tool: Mode) -> None:
        self.tools_screen.message_label.setText("")

        if tool.screen == ScreenKey.REPLAYER:
            self.replay_last_hand()
        elif tool.screen == ScreenKey.EQUITY:
            self.push(self.equity_screen)
        elif tool.screen == ScreenKey.MY_STATS:
            self._show_my_stats()
            self.push(self.my_stats_screen)
        elif tool.screen == ScreenKey.SESSIONS:
            self.session_browser_screen.refresh()
            self.push(self.session_browser_screen)

    def replay_last_hand(self) -> None:
        """Open the replayer on the last hand of the latest session."""
        latest = next(
            (session for session in self.library.scan().sessions if session.hands),
            None,
        )

        if latest is None:
            self.tools_screen.message_label.setText(
                "No saved hand yet: play a game first, then replay it here."
            )
            return

        self.replay_hand(latest, len(latest.hands) - 1)

    def replay_hand(self, session: SessionRecord, index: int) -> None:
        self.replayer_screen.show_hand(session, index)
        self.push(self.replayer_screen)

    def _show_my_stats(self) -> None:
        self.my_stats_screen.show_scan(self.library.scan())

    # --- Bot Arena -----------------------------------------------------------

    def run_arena(self, config: SimulationConfig | TournamentRunConfig) -> None:
        self.push(self.arena_progress_screen)
        self.arena_progress_screen.start(config)

    def rerun_arena(self, config: SimulationConfig | TournamentRunConfig) -> None:
        self.replace(self.arena_progress_screen)
        self.arena_progress_screen.start(config)

    def show_arena_result(self, result: SimulationResult | TournamentRunResult) -> None:
        assert result.config.seed is not None
        self.arena_setup_screen.show_last_seed(result.config.seed)
        self.arena_results_screen.show_result(result)
        self.replace(self.arena_results_screen)

    def watch_arena(self, config: SimulationConfig) -> None:
        self.push(self.arena_watch_screen)
        self.arena_watch_screen.start(config)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Quitting closes every table first: a running tournament asks, and
        staying at it cancels the quit."""
        if self.settings_dialog is not None:
            self.settings_dialog.close()

        for window in list(self.game_windows):
            if not window.close():
                event.ignore()
                return

        # Never leave worker processes behind.
        self.arena_progress_screen.cancel()
        self.arena_progress_screen.wait()
        self.arena_watch_screen.stop()
        self.replayer_screen.stop()
        self.equity_screen.stop()
        super().closeEvent(event)
