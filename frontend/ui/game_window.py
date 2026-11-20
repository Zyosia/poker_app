"""One game in its own window: its setup screen, its table, its results.

Each Cash Game, Tournament or Spin & Go opens in a window of its own, so
several games are played at once (multi-tabling). The lobby (``MainWindow``)
owns the profile, the sounds and the settings that every window shares,
and brings the table waiting for you to the front.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QLabel, QWidget

from backend.application.action_clock import ClockPreset, clock_preset
from backend.application.bankroll import GameAccount, InsufficientFundsError
from backend.application.controllers import HumanController
from backend.application.game import PokerGame
from backend.application.game_modes import MODE_LABELS, GameMode
from backend.application.hand_records import live_session_record
from backend.application.profile import BotCards, UserSettings
from backend.application.setup import (
    QUICK_SPIN_CLOCK,
    GameSettings,
    SpinSettings,
    TournamentSettings,
    create_game,
    create_spin_and_go,
    create_tournament,
)
from backend.application.tournament import Tournament
from frontend.pacing import DEFAULT_TABLE_SPEED

from .bankroll_screen import BankrollScreen
from .cash_setup_screen import CashSetupScreen
from .game_screen import GameScreen
from .navigation_window import NavigationWindow
from .replayer_window import ReplayerWindow, last_replayable_hand
from .spin_quick_screen import SpinQuickScreen
from .table_spectator_window import TableSpectatorWindow
from .tournament_lobby import TournamentLobbyWindow
from .tournament_results_screen import TournamentResultsScreen
from .tournament_screen import TournamentScreen
from .tournament_setup_screen import SpinSetupScreen, TournamentSetupScreen

if TYPE_CHECKING:
    from .main_window import MainWindow

PlayedSettings = TournamentSettings | SpinSettings
SetupScreen = CashSetupScreen | TournamentSetupScreen | SpinSetupScreen
CLOCK_SETTINGS = {
    GameMode.CASH: "cash_clock",
    GameMode.TOURNAMENT: "tournament_clock",
    GameMode.SPIN: "spin_clock",
}
"""The user's clock choice for each mode's setup screen."""
YOUR_TURN = "Your turn"
TILE_SHORTCUT = "Ctrl+T"
WINDOW_SIZE = (1180, 820)
"""At most: a smaller screen gets a smaller window."""
MIN_WINDOW_SIZE = (820, 480)
"""Small enough for four tables side by side on a full HD screen."""


class GameWindow(NavigationWindow):
    """A Cash Game, a Tournament or a Spin & Go, from its setup on."""

    your_turn_changed = Signal(object, bool)
    """(this window, whether its table now waits for you)."""
    closed = Signal(object)

    def __init__(self, mode: GameMode, lobby: "MainWindow", number: int) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(*WINDOW_SIZE)
        self.setMinimumSize(*MIN_WINDOW_SIZE)

        self.mode = mode
        self.lobby = lobby
        self.number = number
        """Table 1, 2...: the lowest number free when the window opened."""
        self.game_name = MODE_LABELS[mode]
        self._played_settings: PlayedSettings | None = None
        self._played_clock: ClockPreset | None = None
        self._quick_buy_in: int | None = None
        """The buy-in of a Spin & Go started in one click (None: set up)."""
        self.replayer_window: ReplayerWindow | None = None
        self.lobby_window: TournamentLobbyWindow | None = None
        self.spectator_windows: dict[int, TableSpectatorWindow] = {}
        """The other tables of the tournament watched, by number (V3.1.1)."""

        self.quick_screen: SpinQuickScreen | None = (
            SpinQuickScreen() if mode == GameMode.SPIN else None
        )
        """The Spin & Go started in one click, before the custom setup (V3.2)."""
        self.setup_screen = self._create_setup_screen()
        self.table_screen: GameScreen = (
            GameScreen() if mode == GameMode.CASH else TournamentScreen()
        )
        self.results_screen = TournamentResultsScreen()
        self.bankroll_screen = BankrollScreen()
        self.screens.setObjectName("tableFrame")
        self.add_screens(
            *([self.quick_screen] if self.quick_screen is not None else []),
            self.setup_screen,
            self.table_screen,
            self.results_screen,
            self.bankroll_screen,
        )
        self.show_first(self.quick_screen or self.setup_screen)
        self._connect()
        self.apply_settings(lobby.profile.settings)
        self._update_title()

    def _create_setup_screen(self) -> SetupScreen:
        setup: SetupScreen

        if self.mode == GameMode.CASH:
            setup = CashSetupScreen()
            setup.start_requested.connect(self.start_game)
        elif self.mode == GameMode.TOURNAMENT:
            setup = TournamentSetupScreen()
            setup.start_requested.connect(self.play_tournament)
        else:
            setup = SpinSetupScreen()
            setup.start_requested.connect(self.play_tournament)

        setting = CLOCK_SETTINGS[self.mode]
        stored = getattr(self.lobby.profile.settings, setting)

        if stored:
            setup.clock_combo.set_choice(stored, user_chosen=True)

        setup.clock_combo.chosen.connect(
            lambda name: self.lobby.save_setting(setting, name)
        )

        return setup

    def _connect(self) -> None:
        lobby = self.lobby
        setup = self.setup_screen
        table = self.table_screen

        quick = self.quick_screen
        setup.bankroll_bar.bankroll_requested.connect(self.open_bankroll)
        setup.bankroll_bar.reload_requested.connect(lobby.reload_bankroll)

        if quick is None:
            setup.back_requested.connect(self.close)
        else:
            setup.back_requested.connect(self.back)
            quick.back_requested.connect(self.close)
            quick.custom_requested.connect(lambda: self.push(self.setup_screen))
            quick.start_requested.connect(self.play_quick_spin)
            quick.bankroll_bar.bankroll_requested.connect(self.open_bankroll)
            quick.bankroll_bar.reload_requested.connect(lobby.reload_bankroll)
        self.bankroll_screen.back_requested.connect(self.back)
        self.bankroll_screen.changed.connect(
            lambda: lobby.on_bankroll_screen_changed(self.bankroll_screen)
        )

        table.sounds = lobby.sounds
        table.show_in_big_blinds_changed.connect(lobby.set_show_in_big_blinds)
        table.show_bot_styles_changed.connect(lobby.set_show_bot_styles)
        table.speed_changed.connect(lobby.set_table_speed)
        table.auto_next_hand_changed.connect(lobby.set_auto_next_hand)
        table.history_shown_changed.connect(lobby.set_show_history)
        table.tile_requested.connect(lobby.tile_tables)
        table.replay_requested.connect(self.replay_last_hand)
        QShortcut(QKeySequence(TILE_SHORTCUT), self, lobby.tile_tables)
        table.your_turn_changed.connect(self._on_your_turn_changed)

        if isinstance(table, TournamentScreen):
            table.menu_requested.connect(self.back_to_first)
            table.finished.connect(self.show_tournament_results)
            table.lobby_requested.connect(self.open_lobby)
            table.standings_changed.connect(self._refresh_lobby)
            table.live_tables_stepped.connect(self._refresh_spectators)
            self.results_screen.play_again_requested.connect(self.play_again)
            self.results_screen.menu_requested.connect(self.back_to_first)
        else:
            table.menu_requested.connect(self.back)

    # --- Settings and bankroll ------------------------------------------------

    def apply_settings(self, settings: UserSettings) -> None:
        """Show this window as the user's settings say."""
        table = self.table_screen
        table.set_show_in_big_blinds(settings.show_in_big_blinds)
        table.set_speed(settings.table_speed or DEFAULT_TABLE_SPEED)
        table.set_auto_next_hand(settings.auto_next_hand)
        table.set_history_shown(settings.show_history)
        table.turn_alert = settings.turn_alert
        table.set_bot_cards(BotCards(settings.bot_cards))
        table.set_show_bot_styles(settings.show_bot_styles)
        self.setup_screen.set_player_name(settings.player_name)

        if self.quick_screen is not None:
            self.quick_screen.set_player_name(settings.player_name)

        self.refresh_bankroll()

    def refresh_bankroll(self) -> None:
        bankroll = self.lobby.profile.bankroll
        hints = self.lobby.profile.settings.bankroll_hints
        self.setup_screen.bankroll_bar.set_balance(
            bankroll.balance, bankroll.can_reload
        )
        self.setup_screen.set_bankroll(bankroll.balance, hints)

        if self.quick_screen is not None:
            self.quick_screen.bankroll_bar.set_balance(
                bankroll.balance, bankroll.can_reload
            )
            self.quick_screen.set_bankroll(bankroll.balance, hints)

        if self.current_screen is self.bankroll_screen:
            self.bankroll_screen.refresh()

    def open_bankroll(self) -> None:
        profile = self.lobby.profile
        self.bankroll_screen.show_bankroll(
            profile.bankroll, profile.settings.bankroll_hints
        )
        self.push(self.bankroll_screen)

    # --- Your turn --------------------------------------------------------------

    @property
    def your_turn(self) -> bool:
        return self.table_screen.your_turn

    @property
    def is_playing(self) -> bool:
        """A game runs at this window's table."""
        return self.table_screen.game is not None

    def table_to_pause(self) -> GameScreen | None:
        """The table, if it runs (the Spin & Go draw goes on: it deals the
        first hand)."""
        table = self.table_screen

        if table.game is None or table.paused or self.current_screen is not table:
            return None

        if isinstance(table, TournamentScreen) and table.is_revealing:
            return None

        return table

    def _on_your_turn_changed(self, waiting: bool) -> None:
        self.screens.setProperty("yourTurn", waiting)
        self.screens.style().unpolish(self.screens)
        self.screens.style().polish(self.screens)
        self._update_title()
        self.your_turn_changed.emit(self, waiting)

    def _update_title(self) -> None:
        title = f"{self.game_name} — Table {self.number}"
        self.setWindowTitle(f"{YOUR_TURN} · {title}" if self.your_turn else title)

    @property
    def title(self) -> str:
        """The name of the table, as the lobby lists it."""
        return f"{self.game_name} · Table {self.number}"

    # --- Cash game ----------------------------------------------------------------

    def start_game(self, settings: GameSettings) -> None:
        """Pay the buy-in, create a game from the settings and show the table."""
        stakes = f"{settings.small_blind}/{settings.big_blind}"
        account = self.lobby.new_account(GameMode.CASH, f"Cash game {stakes}")

        try:
            account.start(buy_in=settings.starting_stack, stack=settings.starting_stack)
        except InsufficientFundsError as error:
            self.setup_screen.error_label.setText(str(error))
            return

        game = create_game(
            settings=settings,
            human_controller=HumanController(),
            save_path=self.lobby.new_save_path(),
        )
        self.game_name = f"Cash game {stakes}"
        self._update_title()
        self.push(self.table_screen)
        self.table_screen.auto_top_up = settings.auto_top_up
        self.table_screen.start_game(
            game,
            human_name=settings.player_name,
            clock=self.setup_screen.clock_combo.preset(),
            account=account,
        )

    # --- Tournament and Spin & Go -----------------------------------------------

    @property
    def tournament_screen(self) -> TournamentScreen:
        table = self.table_screen
        assert isinstance(table, TournamentScreen)

        return table

    def play_tournament(self, settings: PlayedSettings) -> None:
        """Pay the buy-in, start a tournament or a Spin & Go, show its table."""
        setup = self.setup_screen
        self._play(settings, setup.clock_combo.preset(), setup.error_label)
        self._quick_buy_in = None

    def play_quick_spin(self, settings: SpinSettings) -> None:
        """A Spin & Go started in one click, on the Standard clock (V3.2)."""
        assert self.quick_screen is not None

        if self._play(
            settings, clock_preset(QUICK_SPIN_CLOCK), self.quick_screen.error_label
        ):
            self._quick_buy_in = settings.buy_in

    def _play(
        self, settings: PlayedSettings, clock: ClockPreset | None, errors: QLabel
    ) -> bool:
        account = self._pay_buy_in(settings)

        if account is None:
            errors.setText("Not enough money in your bankroll.")
            return False

        self._played_settings = settings
        self._played_clock = clock
        self.push(self.table_screen)
        self._start_played(settings, account)

        return True

    def play_again(self) -> None:
        """The same game again; a Spin & Go started in one click draws two
        new bots."""
        settings = self._played_settings

        if settings is None:
            return

        if self._quick_buy_in is not None and self.quick_screen is not None:
            settings = self.quick_screen.settings_for(self._quick_buy_in)

        account = self._pay_buy_in(settings)

        if account is not None:
            self._played_settings = settings
            self.replace(self.table_screen)
            self._start_played(settings, account)

    def _pay_buy_in(self, settings: PlayedSettings) -> GameAccount | None:
        """Pay a tournament's buy-in; None if the bankroll cannot."""
        if isinstance(settings, SpinSettings):
            account = self.lobby.new_account(GameMode.SPIN, "Spin & Go")
        else:
            account = self.lobby.new_account(
                GameMode.TOURNAMENT, f"Tournament ({settings.structure})"
            )

        try:
            account.start(buy_in=settings.buy_in)
        except InsufficientFundsError:
            return None

        return account

    def _start_played(self, settings: PlayedSettings, account: GameAccount) -> None:
        rng = self.lobby.new_rng()

        if isinstance(settings, SpinSettings):
            tournament = create_spin_and_go(settings, HumanController(), rng)
        else:
            tournament = create_tournament(settings, HumanController(), rng)

        self.tournament_screen.start_tournament(
            tournament,
            human_name=settings.player_name,
            save_path=self.lobby.new_save_path(),
            clock=self._played_clock,
            account=account,
        )

        self._close_spectators()

        if tournament.multi_table:
            self.open_lobby()
        elif self.lobby_window is not None:
            self.lobby_window.close()

    # --- Tournament lobby (V3.1) --------------------------------------------------

    def open_lobby(self) -> TournamentLobbyWindow | None:
        """The lobby of the tournament played here, in a window of its own."""
        table = self.table_screen

        if not isinstance(table, TournamentScreen) or table.game is None:
            return None

        if self.lobby_window is None:
            self.lobby_window = TournamentLobbyWindow(self.title)
            self.lobby_window.watch_requested.connect(self.watch_table)

        self.lobby_window.show_tournament(table.tournament, table.human_name)

        return self.lobby_window

    def watch_table(self, number: int) -> TableSpectatorWindow | None:
        """Watch another table of the tournament in a window of its own."""
        table = self.table_screen

        if not isinstance(table, TournamentScreen) or table.game is None:
            return None

        window = self.spectator_windows.get(number)

        if window is None:
            window = TableSpectatorWindow(table.tournament, number, self.title)
            self.spectator_windows[number] = window

        window.set_display(
            table.bot_cards, table.show_in_big_blinds, table.show_bot_styles
        )
        window.refresh()
        window.show()
        window.raise_()

        return window

    def _refresh_spectators(self) -> None:
        table = self.table_screen

        for window in self.spectator_windows.values():
            if window.isVisible():
                window.set_display(
                    table.bot_cards, table.show_in_big_blinds, table.show_bot_styles
                )
                window.refresh()

    def _close_spectators(self) -> None:
        for window in self.spectator_windows.values():
            window.close()
            window.deleteLater()

        self.spectator_windows.clear()

    def _refresh_lobby(self) -> None:
        lobby = self.lobby_window

        if lobby is not None and lobby.isVisible():
            lobby.refresh()

    def show_tournament_results(self, tournament: Tournament) -> None:
        assert self._played_settings is not None
        self.results_screen.show_tournament(
            tournament, self._played_settings.player_name
        )
        self.results_screen.play_again_button.setEnabled(
            self.lobby.profile.bankroll.can_afford(self._played_settings.buy_in)
        )
        self.replace(self.results_screen)

    # --- Leaving --------------------------------------------------------------------

    def stop_screen(self, screen: QWidget) -> None:
        if screen is self.table_screen:
            self.table_screen.stop()

    # --- Replayer -----------------------------------------------------------------

    def replay_last_hand(self) -> ReplayerWindow | None:
        """Open the replayer, in a window of its own, on the last hand
        played at this table; the game goes on meanwhile."""
        table = self.table_screen
        game = table.game

        if game is None:
            return None

        session = live_session_record(game.session, table.human_name, self.mode)
        index = last_replayable_hand(session)

        if index is None:
            return None

        if self.replayer_window is None:
            self.replayer_window = ReplayerWindow(self.windowTitle())

        replayer = self.replayer_window.replayer
        replayer.set_show_in_big_blinds(self.lobby.profile.settings.show_in_big_blinds)
        self.replayer_window.show_hand(session, index)

        return self.replayer_window

    def save_path_in_use(self) -> Path | None:
        """The session file this window's game is writing, if any."""
        table = self.table_screen
        game = table.game

        if game is None:
            return None

        if isinstance(game, PokerGame):
            return game.save_path

        return table.save_path if isinstance(table, TournamentScreen) else None

    def closeEvent(self, event: QCloseEvent) -> None:
        """A running tournament asks first (it is forfeited); a cash game is
        cashed out."""
        table = self.table_screen

        if isinstance(table, TournamentScreen) and not table.prepare_to_leave():
            event.ignore()
            return

        for window in (self.replayer_window, self.lobby_window):
            if window is not None:
                window.close()
                window.deleteLater()

        self.replayer_window = None
        self.lobby_window = None
        self._close_spectators()

        table.stop()
        self.closed.emit(self)
        super().closeEvent(event)
