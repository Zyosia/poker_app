"""The kinds of game a user plays: recorded by the bankroll and the session files."""

from enum import StrEnum

from backend.poker_engine.constants import (
    FIXED_LIMIT_BET_CAP,
    BettingRules,
    BettingStructure,
)


class GameMode(StrEnum):
    CASH = "cash"
    TOURNAMENT = "tournament"
    SPIN = "spin"


MODE_LABELS = {
    GameMode.CASH: "Cash game",
    GameMode.TOURNAMENT: "Tournament",
    GameMode.SPIN: "Spin & Go",
}


BETTING_LABELS = {
    BettingStructure.NO_LIMIT: "No Limit",
    BettingStructure.POT_LIMIT: "Pot Limit",
    BettingStructure.FIXED_LIMIT: "Fixed Limit",
}
BETTING_SHORT_LABELS = {
    BettingStructure.NO_LIMIT: "NL",
    BettingStructure.POT_LIMIT: "PL",
    BettingStructure.FIXED_LIMIT: "FL",
}


def _shown_cap(rules: BettingRules) -> int | None:
    """The cap worth showing: none for the usual Fixed Limit cap."""
    if rules.structure == BettingStructure.FIXED_LIMIT and (
        rules.cap == FIXED_LIMIT_BET_CAP
    ):
        return None

    return rules.cap


def betting_label(rules: BettingRules) -> str:
    """The structure and its cap: "No Limit", "Pot Limit, cap 3 bets"...

    The usual Fixed Limit cap of four bets is not repeated.
    """
    label = BETTING_LABELS[rules.structure]
    cap = _shown_cap(rules)

    return label if cap is None else f"{label}, cap {cap} bets"


def betting_short_label(rules: BettingRules) -> str:
    """The same, short: "NL", "PL", "FL", "NL cap 3"..."""
    label = BETTING_SHORT_LABELS[rules.structure]
    cap = _shown_cap(rules)

    return label if cap is None else f"{label} cap {cap}"


def game_name(rules: BettingRules) -> str:
    """The game played: "No Limit Hold'em", "Fixed Limit Hold'em"..."""
    return f"{BETTING_LABELS[rules.structure]} Hold'em"
