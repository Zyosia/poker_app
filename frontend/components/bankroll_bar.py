"""The bankroll in a screen's corner: the balance, Reload and Bankroll."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from frontend.formatting import format_chips


class BankrollBar(QWidget):
    """Shown on the main menu and on the setup screens of the paid modes."""

    bankroll_requested = Signal()
    """The Bankroll screen: Back returns to the screen showing this bar."""
    reload_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.balance_label = QLabel()
        self.balance_label.setObjectName("statusText")
        self.bankroll_button = QPushButton("Bankroll")
        self.bankroll_button.setObjectName("small")
        self.bankroll_button.setToolTip("Your balance, results and every transaction.")
        self.bankroll_button.clicked.connect(self.bankroll_requested)
        self.reload_button = QPushButton("Reload")
        self.reload_button.setObjectName("accent")
        self.reload_button.setToolTip("Back to the default bankroll.")
        self.reload_button.clicked.connect(self.reload_requested)
        self.reload_button.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.balance_label)
        layout.addWidget(self.reload_button)
        layout.addWidget(self.bankroll_button)

    def set_balance(self, balance: int, can_reload: bool) -> None:
        """Show the bankroll, and the reload offer when nearly broke."""
        self.balance_label.setText(f"Bankroll  {format_chips(balance)}")
        self.reload_button.setVisible(can_reload)
