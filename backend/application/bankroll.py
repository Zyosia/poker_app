"""The user's bankroll: a balance of fictional money and its ledger.

Every money movement is one ``Transaction``: buy-ins, rebuys and add-ons
(negative), cash-outs and prizes (positive), and adjustments made by the user
(set, reset, reload). Bot Arena never touches the bankroll.

Rules:

- **Cash game**: the starting stack is paid when the session starts, every
  rebuy is paid, and the stack is cashed out when the player leaves. The
  stack behind (chips not in the pot) is kept up to date while playing; if
  the application closes during a session, that stack is cashed out at the
  next launch, so chips already in the pot are lost, as with a fold.
- **Tournament / Spin & Go**: the buy-in is paid at the start, rebuys and the
  add-on when taken, and the prize is credited when the tournament is over.
  Leaving a tournament still running forfeits it (the buy-in is lost); so
  does closing the application during one.

Several games can be open at once (multi-tabling): each has its own account
and its own entry in ``Bankroll.open_games``.

There is no real money anywhere in the application.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from .game_modes import MODE_LABELS, GameMode

DEFAULT_BALANCE = 100_000
RELOAD_THRESHOLD = 1_000
"""Below this balance, the main menu offers a reload to the default."""

RECOMMENDED_BUY_INS = {"cash": 20, "tournament": 50, "spin": 50}
"""Rules of thumb: buy-ins a bankroll should hold for each mode."""


class TransactionType(StrEnum):
    BUY_IN = "buy_in"
    REBUY = "rebuy"
    TOP_UP = "top_up"
    ADD_ON = "add_on"
    CASH_OUT = "cash_out"
    PRIZE = "prize"
    FORFEIT = "forfeit"
    """A tournament left before its end: nothing is paid back."""
    ADJUSTMENT = "adjustment"


TRANSACTION_LABELS = {
    TransactionType.BUY_IN: "Buy-in",
    TransactionType.REBUY: "Rebuy",
    TransactionType.TOP_UP: "Top-up",
    TransactionType.ADD_ON: "Add-on",
    TransactionType.CASH_OUT: "Cash-out",
    TransactionType.PRIZE: "Prize",
    TransactionType.FORFEIT: "Forfeit",
    TransactionType.ADJUSTMENT: "Adjustment",
}


class InsufficientFundsError(ValueError):
    """The bankroll cannot pay for a buy-in, a rebuy or an add-on."""


class BankrollDataError(ValueError):
    """Saved bankroll data that cannot be read."""


@dataclass(frozen=True)
class Transaction:
    """One movement of money, with the balance it left."""

    time: str
    """Date and time, ISO 8601, to the second."""
    type: TransactionType
    mode: GameMode | None
    """None for adjustments."""
    amount: int
    """Positive when money comes in, negative when it goes out."""
    balance_after: int
    description: str
    game_id: str | None = None
    """The session or tournament the transaction belongs to."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "type": self.type.value,
            "mode": self.mode.value if self.mode is not None else None,
            "amount": self.amount,
            "balance_after": self.balance_after,
            "description": self.description,
            "game_id": self.game_id,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Transaction":
        try:
            mode = data["mode"]

            return cls(
                time=_checked(data["time"], str),
                type=TransactionType(data["type"]),
                mode=GameMode(mode) if mode is not None else None,
                amount=_checked(data["amount"], int),
                balance_after=_checked(data["balance_after"], int),
                description=_checked(data["description"], str),
                game_id=_checked(data["game_id"], str, optional=True),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise BankrollDataError(f"Invalid transaction: {error}") from error


@dataclass
class OpenGame:
    """A game paid from the bankroll and not settled yet (crash recovery)."""

    game_id: str
    mode: GameMode
    description: str
    stack: int = 0
    """Cash games: the player's stack behind, cashed out if the app closes."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "mode": self.mode.value,
            "description": self.description,
            "stack": self.stack,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "OpenGame":
        try:
            return cls(
                game_id=_checked(data["game_id"], str),
                mode=GameMode(data["mode"]),
                description=_checked(data["description"], str),
                stack=_checked(data["stack"], int),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise BankrollDataError(f"Invalid open game: {error}") from error


@dataclass
class Bankroll:
    """The balance, its ledger and the games being played."""

    balance: int = DEFAULT_BALANCE
    transactions: list[Transaction] = field(default_factory=list)
    open_games: list[OpenGame] = field(default_factory=list)
    now: Callable[[], datetime] = field(default=datetime.now, repr=False, compare=False)

    def can_afford(self, amount: int) -> bool:
        return 0 <= amount <= self.balance

    def record(
        self,
        kind: TransactionType,
        mode: GameMode | None,
        amount: int,
        description: str,
        game_id: str | None = None,
    ) -> Transaction:
        """Add a transaction and apply it to the balance.

        A payment (negative amount) the balance cannot cover is refused.
        """
        if amount < 0 and not self.can_afford(-amount):
            raise InsufficientFundsError(
                f"{description} costs {-amount}, but the bankroll holds {self.balance}."
            )

        self.balance += amount
        transaction = Transaction(
            time=self.now().isoformat(timespec="seconds"),
            type=kind,
            mode=mode,
            amount=amount,
            balance_after=self.balance,
            description=description,
            game_id=game_id,
        )
        self.transactions.append(transaction)

        return transaction

    # --- Adjustments ------------------------------------------------------------

    def set_balance(self, balance: int, description: str = "Set bankroll") -> None:
        """Change the balance by hand; the ledger records the difference."""
        if balance < 0:
            raise ValueError("The bankroll cannot be negative.")

        self.record(
            TransactionType.ADJUSTMENT, None, balance - self.balance, description
        )

    def reset(self) -> None:
        self.set_balance(DEFAULT_BALANCE, "Reset to the default bankroll")

    @property
    def can_reload(self) -> bool:
        return self.balance < RELOAD_THRESHOLD

    def reload(self) -> None:
        """Back to the default balance once (almost) broke."""
        if not self.can_reload:
            raise ValueError("A reload is only offered to a nearly empty bankroll.")

        self.set_balance(DEFAULT_BALANCE, "Reload")

    # --- Results ----------------------------------------------------------------

    def net_result(self, mode: GameMode | None = None) -> int:
        """Money won or lost by playing (adjustments excluded)."""
        return sum(
            transaction.amount
            for transaction in self.transactions
            if transaction.mode is not None
            and (mode is None or transaction.mode == mode)
        )

    def balance_history(self) -> list[int]:
        """The balance before the first transaction, then after each one."""
        if not self.transactions:
            return [self.balance]

        first = self.transactions[0]

        return [
            first.balance_after - first.amount,
            *(transaction.balance_after for transaction in self.transactions),
        ]

    # --- Crash recovery ---------------------------------------------------------

    def open_game(self, game_id: str) -> OpenGame | None:
        return next((game for game in self.open_games if game.game_id == game_id), None)

    def recover_open_games(self) -> list[Transaction]:
        """Settle the games the application closed during (see the module rules)."""
        games, self.open_games = self.open_games, []

        return [self._recover(game) for game in games]

    def _recover(self, game: OpenGame) -> Transaction:
        if game.mode == GameMode.CASH:
            return self.record(
                TransactionType.CASH_OUT,
                game.mode,
                game.stack,
                f"{game.description}: stack cashed out after the application "
                "closed during the session",
                game.game_id,
            )

        return self.record(
            TransactionType.FORFEIT,
            game.mode,
            0,
            f"{game.description}: forfeited, the application closed during it",
            game.game_id,
        )

    # --- Saving -----------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "balance": self.balance,
            "transactions": [t.to_dict() for t in self.transactions],
            "open_games": [game.to_dict() for game in self.open_games],
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Bankroll":
        if not isinstance(data, dict):
            raise BankrollDataError("The bankroll is not an object.")

        try:
            balance = _checked(data["balance"], int)
            transactions = data["transactions"]
            open_games = data.get("open_games", [])
            single = data.get("open_game")  # Before multi-tabling (V1.3).
        except (KeyError, TypeError) as error:
            raise BankrollDataError(f"Invalid bankroll: {error}") from error

        if not isinstance(transactions, list) or not isinstance(open_games, list):
            raise BankrollDataError("The bankroll's transactions or games are invalid.")

        if single:
            open_games = [*open_games, single]

        return cls(
            balance=balance,
            transactions=[Transaction.from_dict(item) for item in transactions],
            open_games=[OpenGame.from_dict(item) for item in open_games],
        )


def bankroll_hint(mode: GameMode, buy_in: int, balance: int) -> str | None:
    """A soft warning when one buy-in is a large share of the bankroll."""
    recommended = RECOMMENDED_BUY_INS[mode]

    if buy_in <= 0 or buy_in * recommended <= balance:
        return None

    return (
        f"Your bankroll holds {balance // buy_in} buy-ins; about {recommended} "
        f"are recommended ({MODE_LABELS[mode]})."
    )


class GameAccount:
    """The money of one game: its buy-in, rebuys, add-ons and payout.

    ``save`` is called after every change, so the bankroll on disk is always
    up to date (and a crash can be recovered from).
    """

    def __init__(
        self,
        bankroll: Bankroll,
        mode: GameMode,
        description: str,
        save: Callable[[], None],
    ) -> None:
        self.bankroll = bankroll
        self.mode = mode
        self.description = description
        self._save = save
        self.game_id = _new_game_id(bankroll, mode)
        self.closed = False

    def start(self, buy_in: int, stack: int = 0) -> None:
        """Pay the buy-in; ``stack`` is a cash game's starting stack."""
        self._record(TransactionType.BUY_IN, -buy_in, "buy-in")
        self.bankroll.open_games.append(
            OpenGame(self.game_id, self.mode, self.description, stack=stack)
        )
        self._save()

    def can_pay(self, amount: int) -> bool:
        return not self.closed and self.bankroll.can_afford(amount)

    def pay(self, kind: TransactionType, amount: int) -> None:
        """Pay a rebuy or an add-on."""
        label = TRANSACTION_LABELS[kind].lower()
        self._record(kind, -amount, label)
        self._save()

    def update_stack(self, stack: int) -> None:
        """Keep a cash game's stack behind up to date (saved if it changed)."""
        game = self.bankroll.open_game(self.game_id)

        if self.closed or game is None:
            return

        if game.stack != stack:
            game.stack = stack
            self._save()

    def cash_out(self, stack: int) -> None:
        """Leave a cash game with ``stack``."""
        self._close(TransactionType.CASH_OUT, stack, "cash-out")

    def finish(self, prize: int) -> None:
        """A tournament is over: credit the prize (if any)."""
        if prize > 0:
            self._close(TransactionType.PRIZE, prize, "prize")
        else:
            self._close(None, 0, "")

    def forfeit(self) -> None:
        """Leave a tournament still running: the buy-in is lost."""
        self._close(TransactionType.FORFEIT, 0, "left before the end, forfeited")

    def _record(self, kind: TransactionType, amount: int, what: str) -> None:
        if self.closed:
            raise RuntimeError("This game's account is closed.")

        self.bankroll.record(
            kind, self.mode, amount, f"{self.description}: {what}", self.game_id
        )

    def _close(self, kind: TransactionType | None, amount: int, what: str) -> None:
        if self.closed:
            return

        if kind is not None:
            self._record(kind, amount, what)

        game = self.bankroll.open_game(self.game_id)

        if game is not None:
            self.bankroll.open_games.remove(game)

        self.closed = True
        self._save()


def _new_game_id(bankroll: Bankroll, mode: GameMode) -> str:
    """The mode and the time, unique among the open games (several tables can
    start within the same microsecond)."""
    base = bankroll.now().strftime(f"{mode.value}_%Y%m%d_%H%M%S_%f")
    taken = {game.game_id for game in bankroll.open_games}
    game_id = base
    copy = 1

    while game_id in taken:
        copy += 1
        game_id = f"{base}_{copy}"

    return game_id


def _checked(value: Any, kind: type, optional: bool = False) -> Any:
    """Return ``value`` if it has the exact type ``kind`` (bool is not int)."""
    if optional and value is None:
        return None

    if type(value) is not kind:
        raise TypeError(f"expected {kind.__name__}, got {value!r}")

    return value
