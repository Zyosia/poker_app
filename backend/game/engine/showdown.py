# backend/game/engine/showdown.py

from __future__ import annotations

from ..models.models import (
    Hand,
    Player,
    PotResult,
)
from .hand_evaluator import (
    CATEGORY_FLUSH,
    CATEGORY_FOUR_OF_A_KIND,
    CATEGORY_FULL_HOUSE,
    CATEGORY_HIGH_CARD,
    CATEGORY_PAIR,
    CATEGORY_STRAIGHT,
    CATEGORY_STRAIGHT_FLUSH,
    CATEGORY_THREE_OF_A_KIND,
    CATEGORY_TWO_PAIR,
    HandEvaluation,
    evaluate_hand,
)
from .pots import (
    Pot,
    build_pots,
    total_pot_amount,
)


def resolve_hand(
    hand: Hand,
) -> None:
    """
    Resolve the end of a poker hand.

    If only one player remains, that player wins by fold.

    Otherwise, evaluate every remaining player and distribute
    the main pot and side pots according to hand strength.
    """

    active_players = hand.table.get_active_players()

    if not active_players:
        raise RuntimeError("Cannot resolve a hand with no active players.")

    if len(active_players) == 1:
        resolve_by_fold(
            hand=hand,
            winner=active_players[0],
        )
        return

    if len(hand.community_cards) != 5:
        raise RuntimeError("Showdown requires a complete five-card board.")

    evaluate_showdown(
        hand=hand,
        players=active_players,
    )

    distribute_pots(
        hand=hand,
    )

    hand.finished = True
    hand.current_player = None


def resolve_by_fold(
    hand: Hand,
    winner: Player,
) -> None:
    """
    Award the complete pot to the only remaining player.
    """

    winner.stack += hand.pot

    hand.payouts[winner.name] = (
        hand.payouts.get(
            winner.name,
            0,
        )
        + hand.pot
    )

    hand.winner_by_fold = winner

    hand.pot = 0
    hand.finished = True
    hand.current_player = None


def evaluate_showdown(
    hand: Hand,
    players: list[Player],
) -> None:
    """Evaluate every player still involved in the hand."""

    hand.showdown_evaluations.clear()

    for player in players:
        evaluation = evaluate_hand(
            hole_cards=player.hand,
            community_cards=hand.community_cards,
        )

        hand.showdown_evaluations[player.name] = evaluation


def distribute_pots(
    hand: Hand,
) -> None:
    """
    Build and distribute all pots.

    Main pot and side pots are treated independently.
    """

    players = hand.table.players

    pots = build_pots(
        players=players,
    )

    calculated_pot = total_pot_amount(
        pots,
    )

    if calculated_pot != hand.pot:
        raise RuntimeError(
            "Pot accounting mismatch: "
            f"hand.pot={hand.pot}, "
            f"calculated={calculated_pot}."
        )

    hand.pot_results.clear()
    hand.payouts.clear()

    for pot in pots:
        distribute_single_pot(
            hand=hand,
            pot=pot,
        )

    hand.pot = 0


def distribute_single_pot(
    hand: Hand,
    pot: Pot,
) -> None:
    """Determine winners and distribute one pot."""

    if not pot.eligible_players:
        raise RuntimeError("A pot has no eligible players.")

    eligible_players = list(
        pot.eligible_players,
    )

    winners = get_best_players(
        hand=hand,
        players=eligible_players,
    )

    decisive_tiebreaker = None

    if len(winners) == 1:
        opponents = [player for player in eligible_players if player is not winners[0]]

        decisive_tiebreaker = get_decisive_tiebreaker(
            hand=hand,
            winner=winners[0],
            opponents=opponents,
        )

    payout_by_player = split_pot(
        hand=hand,
        pot=pot,
        winners=winners,
    )

    for player in pot.eligible_players:
        amount = payout_by_player.get(
            player.name,
            0,
        )

        if amount == 0:
            continue

        player.stack += amount

        hand.payouts[player.name] = (
            hand.payouts.get(
                player.name,
                0,
            )
            + amount
        )

    hand.pot_results.append(
        PotResult(
            amount=pot.amount,
            eligible_players=tuple(player.name for player in pot.eligible_players),
            winners=tuple(player.name for player in winners),
            decisive_tiebreaker=(
                decisive_tiebreaker[0] if decisive_tiebreaker else None
            ),
            decisive_value=(decisive_tiebreaker[1] if decisive_tiebreaker else None),
        )
    )


def get_best_players(
    hand: Hand,
    players: list[Player],
) -> list[Player]:
    """Return every player tied for the best hand."""

    if not players:
        raise ValueError("At least one player is required.")

    evaluations: list[tuple[Player, HandEvaluation]] = []

    for player in players:
        evaluation = hand.showdown_evaluations.get(
            player.name,
        )

        if evaluation is None:
            raise RuntimeError(f"No showdown evaluation for {player.name}.")

        evaluations.append(
            (player, evaluation),
        )

    best_key = max(evaluation.comparison_key() for _, evaluation in evaluations)

    return [
        player
        for player, evaluation in evaluations
        if evaluation.comparison_key() == best_key
    ]


def split_pot(
    hand: Hand,
    pot: Pot,
    winners: list[Player],
) -> dict[str, int]:
    """
    Split a pot between tied winners.

    Any odd chip is assigned according to clockwise table
    order, starting from the player immediately left of
    the dealer.
    """

    if not winners:
        raise ValueError("A pot must have at least one winner.")

    base_amount, remainder = divmod(
        pot.amount,
        len(winners),
    )

    payouts: dict[str, int] = {player.name: base_amount for player in winners}

    if remainder == 0:
        return payouts

    winner_names = {player.name for player in winners}

    ordered_players = get_players_left_of_dealer(
        hand=hand,
    )

    ordered_winners = [
        player for player in ordered_players if player.name in winner_names
    ]

    for player in ordered_winners[:remainder]:
        payouts[player.name] += 1

    return payouts


def get_players_left_of_dealer(
    hand: Hand,
) -> list[Player]:
    """Return players in clockwise order starting left of dealer."""

    players = hand.table.players

    if not players:
        return []

    dealer = hand.table.dealer

    dealer_index = players.index(
        dealer,
    )

    ordered = players[dealer_index + 1 :] + players[: dealer_index + 1]

    return ordered


def get_decisive_tiebreaker(
    hand: Hand,
    winner: Player,
    opponents: list[Player],
) -> tuple[str, int] | None:
    """
    Return the tiebreaker that made the winner win.
    """

    winner_evaluation = hand.showdown_evaluations[winner.name]

    for opponent in opponents:
        opponent_evaluation = hand.showdown_evaluations[opponent.name]

        if winner_evaluation.rank != opponent_evaluation.rank:
            continue

        for index, (
            winner_value,
            opponent_value,
        ) in enumerate(
            zip(
                winner_evaluation.tiebreaker,
                opponent_evaluation.tiebreaker,
            )
        ):
            if winner_value == opponent_value:
                continue

            tiebreaker_name = get_tiebreaker_name(
                rank=winner_evaluation.rank,
                index=index,
            )

            if tiebreaker_name is None:
                return None

            return (
                tiebreaker_name,
                winner_value,
            )

    return None


def get_tiebreaker_name(
    rank: int,
    index: int,
) -> str | None:
    """Return a human-readable tiebreaker name."""

    if rank == CATEGORY_PAIR:
        names = (
            "pair",
            "kicker",
            "kicker",
            "kicker",
        )

        return names[index]

    if rank == CATEGORY_TWO_PAIR:
        names = (
            "high pair",
            "low pair",
            "kicker",
        )

        return names[index]

    if rank == CATEGORY_THREE_OF_A_KIND:
        names = (
            "trips",
            "kicker",
            "kicker",
        )

        return names[index]

    if rank == CATEGORY_FOUR_OF_A_KIND:
        names = (
            "quads",
            "kicker",
        )

        return names[index]

    if rank == CATEGORY_HIGH_CARD:
        return "high card"

    if rank == CATEGORY_FLUSH:
        return "high card"

    if rank == CATEGORY_STRAIGHT:
        return "straight"

    if rank == CATEGORY_FULL_HOUSE:
        return "full house"

    if rank == CATEGORY_STRAIGHT_FLUSH:
        return "straight flush"

    return None
