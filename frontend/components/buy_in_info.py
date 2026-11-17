"""The cost of a mode and the bankroll, shown on each setup screen."""

from PySide6.QtWidgets import QLabel, QWidget

from backend.application.bankroll import GameMode, bankroll_hint
from frontend.formatting import format_chips

COLORS = {"ok": "#9aa5b4", "hint": "#f2a33a", "error": "#ff7b7b"}


class BuyInInfo(QLabel):
    """ "Buy-in 1 000 · Bankroll 100 000", with a warning when it matters."""

    def __init__(self, mode: GameMode, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode = mode
        self.setWordWrap(True)
        self.state = "ok"

    def refresh(self, cost: int, balance: int, hints: bool) -> bool:
        """Show the cost against the balance; return True if it is affordable."""
        text = f"Buy-in {format_chips(cost)}   ·   Bankroll {format_chips(balance)}"
        affordable = cost <= balance
        hint = bankroll_hint(self.mode, cost, balance) if hints else None

        if not affordable:
            self.state = "error"
            text += "\nNot enough money in your bankroll for this buy-in."
        elif hint is not None:
            self.state = "hint"
            text += f"\n{hint}"
        else:
            self.state = "ok"

        self.setText(text)
        self.setStyleSheet(f"color: {COLORS[self.state]};")

        return affordable
