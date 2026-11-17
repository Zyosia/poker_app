"""Main window: a stack of screens, starting with the main menu.

Opening a screen pushes it on the navigation stack; Back pops it, so Back
always returns to the previous screen. The settings open from every screen,
in their own small window, with the ⚙ button at the top left.
"""

import random
from pathlib import Path

from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QWidget

from backend.application.bankroll import (
    GameAccount,
    GameMode,
    InsufficientFundsError,
)
from backend.application.controllers import HumanController
from backend.application.hand_records import SessionLibrary, SessionRecord
from backend.application.persistence import SESSION_DIR, new_session_file_path
from backend.application.profile import (
    MAX_VOLUME,
    BotCards,
    ProfileStore,
    UserSettings,
)
from backend.application.setup import (
    GameSettings,
    SpinSettings,
    TournamentSettings,
    create_game,
    create_spin_and_go,
    create_tournament,
)
from backend.application.tournament import Tournament
from backend.simulation.config import SimulationConfig
from backend.simulation.result import SimulationResult
from backend.simulation.tournament_runner import (
    TournamentRunConfig,
    TournamentRunResult,
)
from frontend import theme
from frontend.components.card_widget import CardWidget
from frontend.components.settings_button import SettingsButton
from frontend.modes import MODES, TOOLS, Mode, ScreenKey
from frontend.pacing import DEFAULT_TABLE_SPEED
from frontend.sounds import SoundPlayer

from .arena_progress_screen import ArenaProgressScreen
from .arena_results_screen import ArenaResultsScreen
from .arena_setup_screen import ArenaSetupScreen
from .arena_watch_screen import ArenaWatchScreen
from .bankroll_screen import BankrollScreen
from .cash_setup_screen import CashSetupScreen
from .equity_screen import EquityScreen
from .game_screen import GameScreen
from .main_menu_screen import MainMenuScreen
from .my_stats_screen import MyStatsScreen
from .replayer_screen import ReplayerScreen
from .session_browser_screen import SessionBrowserScreen
from .settings_dialog import SettingsDialog
from .tools_screen import ToolsScreen
from .tournament_results_screen import TournamentResultsScreen
from .tournament_screen import TournamentScreen
from .tournament_setup_screen import SpinSetupScreen, TournamentSetupScreen

PlayedSettings = TournamentSettings | SpinSettings
CLOCK_SETTINGS = ("cash_clock", "tournament_clock", "spin_clock")
"""The user's clock choice for each setup screen, in the same order."""
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
)
"""What Restore defaults resets: the settings window, but not your name."""
SETTINGS_SHORTCUT = "Ctrl+,"


class MainWindow(QMainWindow):
    """Top-level window of the application."""

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
        self._paused_for_settings: GameScreen | None = None
        """The table paused while the settings are open, to restart after."""

        self.main_menu = MainMenuScreen(MODES)
        self.cash_setup_screen = CashSetupScreen()
        self.game_screen = GameScreen()
        self.arena_setup_screen = ArenaSetupScreen()
        self.arena_progress_screen = ArenaProgressScreen()
        self.arena_results_screen = ArenaResultsScreen()
        self.arena_watch_screen = ArenaWatchScreen()
        self.tournament_setup_screen = TournamentSetupScreen()
        self.spin_setup_screen = SpinSetupScreen()
        self.tournament_screen = TournamentScreen()
        self.tournament_results_screen = TournamentResultsScreen()
        self.bankroll_screen = BankrollScreen()
        self.tools_screen = ToolsScreen(TOOLS)
        self.replayer_screen = ReplayerScreen()
        self.equity_screen = EquityScreen()
        self.my_stats_screen = MyStatsScreen()
        self.session_browser_screen = SessionBrowserScreen(self.library)
        self._played_settings: PlayedSettings | None = None

        recovered = self.profile.bankroll.recover_open_game()
        self.startup_notice: str | None = None
        """Told to the user at launch: a game the last run did not settle."""

        if recovered is not None:
            self.profile.save()
            self.startup_notice = (
                f"{recovered.description} ({recovered.amount:+,}).".replace(",", " ")
            )

        self.mode_screens: dict[ScreenKey, QWidget] = {
            ScreenKey.CASH_SETUP: self.cash_setup_screen,
            ScreenKey.ARENA_SETUP: self.arena_setup_screen,
            ScreenKey.TOURNAMENT_SETUP: self.tournament_setup_screen,
            ScreenKey.SPIN_SETUP: self.spin_setup_screen,
            ScreenKey.TOOLS: self.tools_screen,
        }

        self.screens = QStackedWidget()

        for screen in (
            self.main_menu,
            self.cash_setup_screen,
            self.game_screen,
            self.arena_setup_screen,
            self.arena_progress_screen,
            self.arena_results_screen,
            self.arena_watch_screen,
            self.tournament_setup_screen,
            self.spin_setup_screen,
            self.tournament_screen,
            self.tournament_results_screen,
            self.bankroll_screen,
            self.tools_screen,
            self.replayer_screen,
            self.equity_screen,
            self.my_stats_screen,
            self.session_browser_screen,
        ):
            self.screens.addWidget(screen)

        self.setCentralWidget(self.screens)
        self.history: list[QWidget] = [self.main_menu]

        # Above every screen; the tables leave room for it in their top bar.
        self.settings_button = SettingsButton(self)
        self.settings_button.setToolTip(f"Settings ({SETTINGS_SHORTCUT})")
        self.settings_button.setFixedSize(
            theme.SETTINGS_BUTTON_SIZE, theme.SETTINGS_BUTTON_SIZE
        )
        self.settings_button.move(
            theme.SETTINGS_BUTTON_MARGIN, theme.SETTINGS_BUTTON_MARGIN
        )
        self.settings_button.raise_()
        self.settings_button.clicked.connect(self.open_settings)
        QShortcut(QKeySequence(SETTINGS_SHORTCUT), self, self.open_settings)

        self.table_screens = (
            self.game_screen,
            self.tournament_screen,
            self.arena_watch_screen,
            self.replayer_screen,
        )

        for screen in self.table_screens:
            screen.show_in_big_blinds_changed.connect(self.set_show_in_big_blinds)

        self.played_screens = (self.game_screen, self.tournament_screen)
        """The tables you play at: they share the speed, auto next hand, the
        sounds and how the bots' cards are shown."""

        for played in self.played_screens:
            played.sounds = self.sounds
            played.speed_changed.connect(self.set_table_speed)
            played.auto_next_hand_changed.connect(self.set_auto_next_hand)

        self.setup_screens = (
            self.cash_setup_screen,
            self.tournament_setup_screen,
            self.spin_setup_screen,
        )
        self.bankroll_bars = (
            self.main_menu.bankroll_bar,
            *(setup.bankroll_bar for setup in self.setup_screens),
        )
        """Back from the Bankroll screen returns to the screen it was opened on."""

        self.clock_combos = (
            self.cash_setup_screen.clock_combo,
            self.tournament_setup_screen.clock_combo,
            self.spin_setup_screen.clock_combo,
        )

        for combo, setting in zip(self.clock_combos, CLOCK_SETTINGS, strict=True):
            stored = getattr(self.profile.settings, setting)

            if stored:
                combo.set_choice(stored, user_chosen=True)

            combo.chosen.connect(
                lambda name, setting=setting: self._save_setting(setting, name)
            )

        self.main_menu.mode_selected.connect(self.open_mode)
        self.main_menu.quit_requested.connect(self.close)
        for bar in self.bankroll_bars:
            bar.bankroll_requested.connect(self.open_bankroll)
            bar.reload_requested.connect(self.reload_bankroll)

        self.bankroll_screen.back_requested.connect(self.back)
        self.bankroll_screen.changed.connect(self._on_bankroll_screen_changed)
        self.apply_settings()

        self.cash_setup_screen.start_requested.connect(self.start_game)
        self.cash_setup_screen.back_requested.connect(self.back)
        self.game_screen.menu_requested.connect(self.back)

        self.arena_setup_screen.run_requested.connect(self.run_arena)
        self.arena_setup_screen.watch_requested.connect(self.watch_arena)
        self.arena_setup_screen.back_requested.connect(self.back)
        self.arena_progress_screen.finished.connect(self.show_arena_result)
        self.arena_progress_screen.cancelled.connect(self.back)
        self.arena_results_screen.back_requested.connect(self.back)
        self.arena_results_screen.rerun_requested.connect(self.rerun_arena)
        self.arena_watch_screen.back_requested.connect(self.back)

        self.tournament_setup_screen.start_requested.connect(self.play_tournament)
        self.tournament_setup_screen.back_requested.connect(self.back)
        self.spin_setup_screen.start_requested.connect(self.play_tournament)
        self.spin_setup_screen.back_requested.connect(self.back)
        self.tournament_screen.menu_requested.connect(self.back_to_menu)
        self.tournament_screen.finished.connect(self.show_tournament_results)
        self.tournament_results_screen.play_again_requested.connect(self.play_again)
        self.tournament_results_screen.menu_requested.connect(self.back_to_menu)

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
        """Show every screen as the user's settings say."""
        settings = self.profile.settings
        self.sounds.enabled = settings.sound_effects
        self.sounds.set_volume(settings.sound_volume / MAX_VOLUME)

        for screen in self.table_screens:
            screen.set_show_in_big_blinds(settings.show_in_big_blinds)

        for played in self.played_screens:
            played.set_speed(settings.table_speed or DEFAULT_TABLE_SPEED)
            played.set_auto_next_hand(settings.auto_next_hand)
            played.turn_alert = settings.turn_alert
            played.set_bot_cards(BotCards(settings.bot_cards))

        for setup in self.setup_screens:
            setup.set_player_name(settings.player_name)

        if CardWidget.four_colors != settings.four_color_deck:
            CardWidget.four_colors = settings.four_color_deck
            self.update()  # Every card is painted again.

        self.refresh_bankroll()

    def open_settings(self) -> SettingsDialog:
        """Open the settings over the current screen; a table you play at is
        paused meanwhile, and goes on once they are closed."""
        if self.settings_dialog is not None:
            self.settings_dialog.raise_()
            return self.settings_dialog

        table = self._table_to_pause()

        if table is not None:
            table.toggle_pause()
            self._paused_for_settings = table

        dialog = SettingsDialog(self.profile.settings, self.sounds, self)
        dialog.setting_changed.connect(self._on_setting_changed)
        dialog.defaults_requested.connect(self.restore_default_settings)
        dialog.finished.connect(self._on_settings_closed)
        self.settings_dialog = dialog
        dialog.open()

        return dialog

    def _table_to_pause(self) -> GameScreen | None:
        """The table you are playing at, if it is running."""
        tournament = self.tournament_screen

        if self.current_screen is tournament and tournament.is_revealing:
            return None  # The Spin & Go draw goes on: it deals the first hand.

        for played in self.played_screens:
            if (
                played is self.current_screen
                and played.game is not None
                and not played.paused
            ):
                return played

        return None

    def _on_setting_changed(self, name: str, value: object) -> None:
        self._save_setting(name, value)
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
        paused = self._paused_for_settings
        self._paused_for_settings = None

        if dialog is not None:
            dialog.deleteLater()

        if paused is not None and paused.game is not None and paused.paused:
            paused.toggle_pause()

    def set_show_in_big_blinds(self, enabled: bool) -> None:
        """Show amounts in big blinds on every table, and remember it."""
        for screen in self.table_screens:
            screen.set_show_in_big_blinds(enabled)

        self._save_setting("show_in_big_blinds", enabled)

    def set_table_speed(self, name: str) -> None:
        for played in self.played_screens:
            played.set_speed(name)

        self._save_setting("table_speed", name)

    def set_auto_next_hand(self, enabled: bool) -> None:
        for played in self.played_screens:
            played.set_auto_next_hand(enabled)

        self._save_setting("auto_next_hand", enabled)

    def _new_save_path(self) -> Path | None:
        if not self._save_sessions:
            return None

        return new_session_file_path(self.session_dir)

    def _save_setting(self, name: str, value: object) -> None:
        setattr(self.profile.settings, name, value)
        self.profile.save()

    # --- Bankroll ------------------------------------------------------------

    def refresh_bankroll(self) -> None:
        """Show the balance on the menu and the setup screens."""
        bankroll = self.profile.bankroll
        hints = self.profile.settings.bankroll_hints

        for bar in self.bankroll_bars:
            bar.set_balance(bankroll.balance, bankroll.can_reload)

        for screen in self.setup_screens:
            screen.set_bankroll(bankroll.balance, hints)

    def _save_bankroll(self) -> None:
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
            self._save_bankroll()

    def _on_bankroll_screen_changed(self) -> None:
        self.profile.settings.bankroll_hints = self.bankroll_screen.hints_enabled
        self._save_bankroll()

    def _new_account(self, mode: GameMode, description: str) -> GameAccount:
        return GameAccount(
            self.profile.bankroll, mode, description, save=self._save_bankroll
        )

    # --- Navigation ----------------------------------------------------------

    @property
    def current_screen(self) -> QWidget:
        return self.history[-1]

    def push(self, screen: QWidget) -> None:
        """Show a screen; Back returns to the current one."""
        self.history.append(screen)
        self.screens.setCurrentWidget(screen)

    def replace(self, screen: QWidget) -> None:
        """Show a screen in place of the current one."""
        self.history[-1] = screen
        self.screens.setCurrentWidget(screen)

    def back(self) -> None:
        """Return to the previous screen."""
        if len(self.history) == 1:
            return

        leaving = self.history.pop()

        self._stop(leaving)
        self.screens.setCurrentWidget(self.current_screen)
        self.refresh_bankroll()

    def back_to_menu(self) -> None:
        """Leave whatever is shown and return to the main menu."""
        for screen in self.history[1:]:
            self._stop(screen)

        self.history = [self.main_menu]
        self.screens.setCurrentWidget(self.main_menu)
        self.refresh_bankroll()

    def _stop(self, screen: QWidget) -> None:
        if screen is self.game_screen:
            self.game_screen.stop()
        elif screen is self.arena_watch_screen:
            self.arena_watch_screen.stop()
        elif screen is self.tournament_screen:
            self.tournament_screen.stop()
        elif screen is self.replayer_screen:
            self.replayer_screen.stop()
        elif screen is self.equity_screen:
            self.equity_screen.stop()

    def open_mode(self, mode: Mode) -> None:
        if mode.screen is not None:
            self.push(self.mode_screens[mode.screen])

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

    # --- Cash game -----------------------------------------------------------

    def start_game(self, settings: GameSettings) -> None:
        """Pay the buy-in, create a game from the settings and show the table."""
        account = self._new_account(
            GameMode.CASH,
            f"Cash game {settings.small_blind}/{settings.big_blind}",
        )

        try:
            account.start(buy_in=settings.starting_stack, stack=settings.starting_stack)
        except InsufficientFundsError as error:
            self.cash_setup_screen.error_label.setText(str(error))
            return

        game = create_game(
            settings=settings,
            human_controller=HumanController(),
            save_path=self._new_save_path(),
        )

        self.push(self.game_screen)
        self.game_screen.start_game(
            game,
            human_name=settings.player_name,
            clock=self.cash_setup_screen.clock_combo.preset(),
            account=account,
        )

    # --- Tournament and Spin & Go ---------------------------------------------

    def play_tournament(self, settings: PlayedSettings) -> None:
        """Pay the buy-in, start a tournament or a Spin & Go, show its table."""
        account = self._pay_buy_in(settings)

        if account is None:
            setup = (
                self.spin_setup_screen
                if isinstance(settings, SpinSettings)
                else self.tournament_setup_screen
            )
            setup.error_label.setText("Not enough money in your bankroll.")
            return

        self._played_settings = settings
        self.push(self.tournament_screen)
        self._start_played(settings, account)

    def play_again(self) -> None:
        settings = self._played_settings

        if settings is None:
            return

        account = self._pay_buy_in(settings)

        if account is not None:
            self.replace(self.tournament_screen)
            self._start_played(settings, account)

    def _pay_buy_in(self, settings: PlayedSettings) -> GameAccount | None:
        """Pay a tournament's buy-in; None if the bankroll cannot."""
        if isinstance(settings, SpinSettings):
            account = self._new_account(GameMode.SPIN, "Spin & Go")
        else:
            account = self._new_account(
                GameMode.TOURNAMENT, f"Tournament ({settings.structure})"
            )

        try:
            account.start(buy_in=settings.buy_in)
        except InsufficientFundsError:
            return None

        return account

    def _start_played(self, settings: PlayedSettings, account: GameAccount) -> None:
        rng = random.Random(self._rng.getrandbits(64))

        if isinstance(settings, SpinSettings):
            tournament = create_spin_and_go(settings, HumanController(), rng)
            clock = self.spin_setup_screen.clock_combo.preset()
        else:
            tournament = create_tournament(settings, HumanController(), rng)
            clock = self.tournament_setup_screen.clock_combo.preset()

        self.tournament_screen.start_tournament(
            tournament,
            human_name=settings.player_name,
            save_path=self._new_save_path(),
            clock=clock,
            account=account,
        )

    def show_tournament_results(self, tournament: Tournament) -> None:
        assert self._played_settings is not None
        self.tournament_results_screen.show_tournament(
            tournament, self._played_settings.player_name
        )
        self.tournament_results_screen.play_again_button.setEnabled(
            self.profile.bankroll.can_afford(self._played_settings.buy_in)
        )
        self.replace(self.tournament_results_screen)

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
        if self.current_screen is self.tournament_screen and not (
            self.tournament_screen.prepare_to_leave()
        ):
            event.ignore()
            return

        # Never leave worker processes behind.
        self.arena_progress_screen.cancel()
        self.arena_progress_screen.wait()
        self.arena_watch_screen.stop()
        self.game_screen.stop()
        self.tournament_screen.stop()
        self.replayer_screen.stop()
        self.equity_screen.stop()
        super().closeEvent(event)
