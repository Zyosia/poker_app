"""Plain-language reading of a simulation result, based on its confidence intervals."""

import math

from .config import StackPolicy
from .result import SimulationResult
from .stats import CONFIDENCE_Z, PlayerStats


def is_difference_significant(
    first: PlayerStats, second: PlayerStats, big_blind: int
) -> bool | None:
    """Return True when two bb/100 win rates differ at the 95% level.

    Returns None when there are not enough hands to tell.
    """
    first_rate = first.bb_per_100(big_blind)
    second_rate = second.bb_per_100(big_blind)
    first_error = first.standard_error_bb_per_100(big_blind)
    second_error = second.standard_error_bb_per_100(big_blind)

    if None in (first_rate, second_rate, first_error, second_error):
        return None

    assert first_rate is not None and second_rate is not None
    assert first_error is not None and second_error is not None

    margin = CONFIDENCE_Z * math.hypot(first_error, second_error)

    return abs(first_rate - second_rate) > margin


def format_bb_per_100(stats: PlayerStats, big_blind: int) -> str:
    """Format a win rate as "+12.4 bb/100 (±3.1)"."""
    win_rate = stats.bb_per_100(big_blind)
    error = stats.standard_error_bb_per_100(big_blind)

    if win_rate is None:
        return "no hands played"

    if error is None:
        return f"{win_rate:+.1f} bb/100"

    return f"{win_rate:+.1f} bb/100 (±{CONFIDENCE_Z * error:.1f})"


def summarize(result: SimulationResult) -> list[str]:
    """Return a few sentences explaining the result to a player."""
    ranking = result.ranking()

    if not ranking:
        return []

    if result.config.stack_policy == StackPolicy.ELIMINATION:
        return _summarize_elimination(result, ranking)

    big_blind = result.config.big_blind
    best = ranking[0]
    sentences = [f"{best.name} won the most: {format_bb_per_100(best, big_blind)}."]

    if len(ranking) > 1:
        worst = ranking[-1]
        sentences.append(
            f"{worst.name} lost the most: {format_bb_per_100(worst, big_blind)}."
        )

    unclear = [
        f"{first.name} vs {second.name}"
        for first, second in zip(ranking, ranking[1:], strict=False)
        if is_difference_significant(first, second, big_blind) is False
    ]

    if unclear:
        sentences.append(
            "With this sample size, these differences are not significant: "
            + ", ".join(unclear)
            + "."
        )
    elif len(ranking) > 1:
        sentences.append("Every gap in the ranking is statistically significant.")

    if result.config.duplicate:
        sentences.append(
            "Duplicate mode was used: every bot played every deal from every seat."
        )

    return sentences


def _summarize_elimination(
    result: SimulationResult, ranking: list[PlayerStats]
) -> list[str]:
    sessions = result.totals.sessions
    sentences = []

    for stats in ranking[:3]:
        sentences.append(
            f"{stats.name} won {stats.finishes[0] if stats.finishes else 0} of "
            f"{sessions} sessions ({(stats.win_rate or 0.0):.0%}), finishing "
            f"{stats.average_finish or 0.0:.2f} on average."
        )

    if result.totals.capped_sessions:
        sentences.append(
            f"{result.totals.capped_sessions} sessions reached the hand limit and "
            "were ranked by stack."
        )

    return sentences
