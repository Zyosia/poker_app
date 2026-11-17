"""The run-out: what the table shows once no more betting is possible.

When an all-in is called and nobody can bet any more, the engine records the
moment (``Hand.revealed_after_action``). The players still in the hand then
turn their cards face up, and the remaining streets are dealt one by one with
each player's chance of winning under their cards.
"""

import zlib

from backend.application.equity import calculate_equity
from backend.poker_engine.models import Hand

RUNOUT_DELAY_FACTOR = 1.25
"""A street of the run-out takes this many normal steps (800 ms → 1 s)."""


def is_running_out(hand: Hand) -> bool:
    """True while the board is dealt after the betting closed."""
    return hand.revealed_after_action is not None and not hand.finished


def runout_delay_ms(step_delay_ms: int) -> int:
    """The pause before each street of the run-out."""
    return round(step_delay_ms * RUNOUT_DELAY_FACTOR)


def revealed_names(hand: Hand) -> set[str]:
    """Players whose cards are face up because the betting is over."""
    if hand.revealed_after_action is None:
        return set()

    return {player.name for player in hand.table.players if player.is_active}


class RunoutEquity:
    """Each player's equity during the run-out, computed once per street."""

    def __init__(self) -> None:
        self._hand: Hand | None = None
        self._board_size = -1
        self._texts: dict[str, str] = {}

    def texts(self, hand: Hand) -> dict[str, str]:
        """Return "≈ 38%" (estimate before the flop) or "38%" by player name."""
        if not is_running_out(hand):
            return {}

        board = hand.community_cards

        if hand is not self._hand or len(board) != self._board_size:
            self._hand = hand
            self._board_size = len(board)
            self._texts = self._calculate(hand)

        return self._texts

    @staticmethod
    def _calculate(hand: Hand) -> dict[str, str]:
        players = [
            player
            for player in hand.table.players
            if player.is_active and len(player.hand) == 2
        ]

        if len(players) < 2:
            return {}

        hands = [tuple(player.hand) for player in players]
        # The estimate's RNG is seeded from the cards on the table: the same
        # situation shows the same numbers, and the game's RNG is untouched.
        seed = zlib.crc32("".join(card for cards in hands for card in cards).encode())
        equity = calculate_equity(hands, list(hand.community_cards), seed=seed)
        prefix = "" if equity.exact else "≈ "

        return {
            player.name: f"{prefix}{share * 100:.0f}%"
            for player, share in zip(players, equity.shares, strict=True)
        }
