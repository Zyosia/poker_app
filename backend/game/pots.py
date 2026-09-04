# game/pots.py

from __future__ import annotations

from dataclasses import dataclass

from .models import Player


@dataclass(frozen=True)
class Pot:
    """
    A poker pot.

    contributors are the players whose chips created
    this pot.

    eligible_players are the players allowed to win it.
    Folded players can contribute to a pot but can never
    win it.
    """

    amount: int
    contributors: tuple[Player, ...]
    eligible_players: tuple[Player, ...]


def build_pots(
    players: list[Player],
) -> list[Pot]:
    """
    Build the main pot and all side pots from player
    total contributions.

    Folded players remain contributors but are excluded
    from eligibility.
    """

    contribution_levels = sorted(
        {
            player.total_contribution
            for player in players
            if player.total_contribution > 0
        }
    )

    pots: list[Pot] = []

    previous_level = 0

    for level in contribution_levels:
        contributors = tuple(
            player for player in players if player.total_contribution >= level
        )

        contribution_delta = level - previous_level

        amount = contribution_delta * len(contributors)

        eligible_players = tuple(player for player in contributors if not player.folded)

        if amount > 0:
            pots.append(
                Pot(
                    amount=amount,
                    contributors=contributors,
                    eligible_players=eligible_players,
                )
            )

        previous_level = level

    return pots


def total_pot_amount(
    pots: list[Pot],
) -> int:
    """Return the total amount represented by all pots."""

    return sum(pot.amount for pot in pots)
