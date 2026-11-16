"""Main pot and side pot construction."""

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
    dead_money: int = 0,
) -> list[Pot]:
    """
    Build the main pot and all side pots from player
    total contributions.

    Folded players remain contributors but are excluded
    from eligibility.

    ``dead_money`` (a big-blind ante) is no player's contribution: it goes
    into the main pot. Chips that only folded players put in, above every
    remaining player's contribution, are dead money too: they join the
    highest pot that a remaining player can still win.
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
            if not eligible_players and pots:
                pots[-1] = _with_dead_money(pots[-1], amount, contributors)
            else:
                pots.append(
                    Pot(
                        amount=amount,
                        contributors=contributors,
                        eligible_players=eligible_players,
                    )
                )

        previous_level = level

    if dead_money:
        if not pots:
            raise ValueError("Dead money needs players in the hand.")

        pots[0] = _with_dead_money(pots[0], dead_money, ())

    return pots


def _with_dead_money(pot: Pot, amount: int, contributors: tuple[Player, ...]) -> Pot:
    """Return ``pot`` with ``amount`` more chips, put in by ``contributors``."""
    added = tuple(player for player in contributors if player not in pot.contributors)

    return Pot(
        amount=pot.amount + amount,
        contributors=pot.contributors + added,
        eligible_players=pot.eligible_players,
    )


def total_pot_amount(
    pots: list[Pot],
) -> int:
    """Return the total amount represented by all pots."""

    return sum(pot.amount for pot in pots)
