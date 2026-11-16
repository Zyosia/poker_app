"""End of a hand: showdown, pot distribution and wins by fold."""

from .hand_evaluator import HandCategory, evaluate_hand
from .models import Hand, Player, PotResult
from .pots import Pot, build_pots, total_pot_amount

TIEBREAKER_NAMES: dict[HandCategory, tuple[str, ...]] = {
    HandCategory.HIGH_CARD: ("high card",) * 5,
    HandCategory.PAIR: ("pair", "kicker", "kicker", "kicker"),
    HandCategory.TWO_PAIR: ("high pair", "low pair", "kicker"),
    HandCategory.THREE_OF_A_KIND: ("trips", "kicker", "kicker"),
    HandCategory.STRAIGHT: ("straight",),
    HandCategory.FLUSH: ("high card",) * 5,
    HandCategory.FULL_HOUSE: ("full house", "full house"),
    HandCategory.FOUR_OF_A_KIND: ("quads", "kicker"),
    HandCategory.STRAIGHT_FLUSH: ("straight flush",),
}


def resolve_hand(hand: Hand) -> None:
    """Resolve the end of a poker hand.

    If only one player remains, that player wins by fold. Otherwise every
    remaining player is evaluated and the main pot and side pots are
    distributed according to hand strength.
    """
    active_players = hand.table.get_active_players()

    if not active_players:
        raise RuntimeError("Cannot resolve a hand with no active players.")

    if len(active_players) == 1:
        resolve_by_fold(hand=hand, winner=active_players[0])
        return

    if len(hand.community_cards) != 5:
        raise RuntimeError("Showdown requires a complete five-card board.")

    evaluate_showdown(hand=hand, players=active_players)
    distribute_pots(hand=hand)

    hand.finished = True
    hand.current_player = None


def resolve_by_fold(hand: Hand, winner: Player) -> None:
    """Award the complete pot to the only remaining player."""
    winner.stack += hand.pot
    hand.payouts[winner.name] = hand.payouts.get(winner.name, 0) + hand.pot

    hand.winner_by_fold = winner
    hand.pot = 0
    hand.finished = True
    hand.current_player = None


def evaluate_showdown(hand: Hand, players: list[Player]) -> None:
    """Evaluate every player still involved in the hand."""
    hand.showdown_evaluations.clear()

    for player in players:
        hand.showdown_evaluations[player.name] = evaluate_hand(
            hole_cards=player.hand,
            community_cards=hand.community_cards,
        )


def distribute_pots(hand: Hand) -> None:
    """Build and distribute the main pot and every side pot independently."""
    pots = build_pots(players=hand.table.players)
    calculated_pot = total_pot_amount(pots)

    if calculated_pot != hand.pot:
        raise RuntimeError(
            f"Pot accounting mismatch: hand.pot={hand.pot}, "
            f"calculated={calculated_pot}."
        )

    hand.pot_results.clear()
    hand.payouts.clear()

    for pot in pots:
        distribute_single_pot(hand=hand, pot=pot)

    hand.pot = 0


def distribute_single_pot(hand: Hand, pot: Pot) -> None:
    """Determine the winners of one pot and pay them."""
    if not pot.eligible_players:
        raise RuntimeError("A pot has no eligible players.")

    eligible_players = list(pot.eligible_players)
    winners = get_best_players(hand=hand, players=eligible_players)

    decisive_tiebreaker = None

    if len(winners) == 1:
        decisive_tiebreaker = get_decisive_tiebreaker(
            hand=hand,
            winner=winners[0],
            opponents=[
                player for player in eligible_players if player is not winners[0]
            ],
        )

    for player_name, amount in split_pot(hand=hand, pot=pot, winners=winners).items():
        if amount == 0:
            continue

        winner = next(player for player in winners if player.name == player_name)
        winner.stack += amount
        hand.payouts[player_name] = hand.payouts.get(player_name, 0) + amount

    hand.pot_results.append(
        PotResult(
            amount=pot.amount,
            eligible_players=tuple(player.name for player in eligible_players),
            winners=tuple(player.name for player in winners),
            decisive_tiebreaker=decisive_tiebreaker[0] if decisive_tiebreaker else None,
            decisive_value=decisive_tiebreaker[1] if decisive_tiebreaker else None,
        )
    )


def get_best_players(hand: Hand, players: list[Player]) -> list[Player]:
    """Return every player tied for the best hand."""
    if not players:
        raise ValueError("At least one player is required.")

    keys: dict[str, tuple[int, ...]] = {}

    for player in players:
        evaluation = hand.showdown_evaluations.get(player.name)

        if evaluation is None:
            raise RuntimeError(f"No showdown evaluation for {player.name}.")

        keys[player.name] = evaluation.comparison_key()

    best_key = max(keys.values())

    return [player for player in players if keys[player.name] == best_key]


def split_pot(hand: Hand, pot: Pot, winners: list[Player]) -> dict[str, int]:
    """Split a pot between tied winners.

    Odd chips are assigned one by one in clockwise table order, starting with
    the winner closest to the left of the dealer.
    """
    if not winners:
        raise ValueError("A pot must have at least one winner.")

    base_amount, remainder = divmod(pot.amount, len(winners))
    payouts = {player.name: base_amount for player in winners}

    if remainder == 0:
        return payouts

    winner_names = set(payouts)
    ordered_winners = [
        player
        for player in get_players_left_of_dealer(hand)
        if player.name in winner_names
    ]

    for player in ordered_winners[:remainder]:
        payouts[player.name] += 1

    return payouts


def get_players_left_of_dealer(hand: Hand) -> list[Player]:
    """Return players in clockwise order starting left of the dealer."""
    if not hand.table.players:
        return []

    return hand.table.players_after(hand.table.dealer)


def get_decisive_tiebreaker(
    hand: Hand,
    winner: Player,
    opponents: list[Player],
) -> tuple[str, int] | None:
    """Return the tiebreaker that beat an opponent holding the same category."""
    winner_evaluation = hand.showdown_evaluations[winner.name]

    for opponent in opponents:
        opponent_evaluation = hand.showdown_evaluations[opponent.name]

        if winner_evaluation.rank != opponent_evaluation.rank:
            continue

        for index, (winner_value, opponent_value) in enumerate(
            zip(
                winner_evaluation.tiebreaker,
                opponent_evaluation.tiebreaker,
                strict=True,
            )
        ):
            if winner_value != opponent_value:
                name = get_tiebreaker_name(rank=winner_evaluation.rank, index=index)
                return (name, winner_value)

    return None


def get_tiebreaker_name(rank: HandCategory, index: int) -> str:
    """Return a human-readable name for one tiebreaker value."""
    return TIEBREAKER_NAMES[rank][index]
