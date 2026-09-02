# game/actions.py

from __future__ import annotations

from game.models import Hand, Player


def put_chips_in_pot(
    player: Player,
    hand: Hand,
    amount: int,
) -> int:
    """
    Move chips from a player's stack into the pot.

    The amount is automatically capped at the player's
    remaining stack, allowing an all-in.
    """

    if amount < 0:
        raise ValueError(
            "Chip amount cannot be negative."
        )

    actual_amount = min(
        amount,
        player.stack,
    )

    player.stack -= actual_amount

    player.current_bet += actual_amount
    player.total_contribution += actual_amount

    hand.pot += actual_amount

    if player.stack == 0:
        player.all_in = True

    return actual_amount


def post_small_blind(
    player: Player,
    hand: Hand,
    amount: int,
) -> int:
    """Post the small blind."""

    return put_chips_in_pot(
        player=player,
        hand=hand,
        amount=amount,
    )


def post_big_blind(
    player: Player,
    hand: Hand,
    amount: int,
) -> int:
    """Post the big blind."""

    posted_amount = put_chips_in_pot(
        player=player,
        hand=hand,
        amount=amount,
    )

    hand.current_bet = posted_amount
    hand.last_raise_size = posted_amount

    return posted_amount


def fold(player: Player) -> None:
    """Fold the player's hand."""

    player.folded = True
    player.acted_this_round = True


def can_check(
    player: Player,
    hand: Hand,
) -> bool:
    """Return True if the player can check."""

    return (
        player.current_bet
        == hand.current_bet
    )


def check(
    player: Player,
    hand: Hand,
) -> None:
    """Check if no additional chips are required."""

    if not can_check(
        player=player,
        hand=hand,
    ):
        raise ValueError(
            "Cannot check. "
            "You must call, raise or fold."
        )

    player.acted_this_round = True


def get_call_amount(
    player: Player,
    hand: Hand,
) -> int:
    """Return the amount required to call."""

    return max(
        0,
        hand.current_bet
        - player.current_bet,
    )


def call(
    player: Player,
    hand: Hand,
) -> int:
    """Call the current bet."""

    amount = get_call_amount(
        player=player,
        hand=hand,
    )

    actual_amount = put_chips_in_pot(
        player=player,
        hand=hand,
        amount=amount,
    )

    player.acted_this_round = True

    return actual_amount


def get_minimum_raise_to(
    hand: Hand,
) -> int:
    """
    Return the minimum legal 'raise to' amount.

    Example:
        current bet = 20
        last raise = 10
        minimum raise to = 30
    """

    if hand.current_bet == 0:
        return 0

    return (
        hand.current_bet
        + hand.last_raise_size
    )


def raise_bet(
    player: Player,
    hand: Hand,
    raise_to: int,
) -> int:
    """
    Raise the current bet to an absolute amount.

    Example:
        current bet = 20
        player already invested = 20
        raise_to = 40

    The player therefore adds 20 chips.
    """

    if raise_to <= hand.current_bet:
        raise ValueError(
            "Raise must be greater than "
            "the current bet."
        )

    minimum_raise_to = get_minimum_raise_to(
        hand,
    )

    if raise_to < minimum_raise_to:
        raise ValueError(
            f"Minimum raise is to {minimum_raise_to}."
        )

    amount_to_add = (
        raise_to
        - player.current_bet
    )

    if amount_to_add > player.stack:
        raise ValueError(
            "Not enough chips for this raise."
        )

    previous_bet = hand.current_bet

    put_chips_in_pot(
        player=player,
        hand=hand,
        amount=amount_to_add,
    )

    new_bet = player.current_bet

    hand.current_bet = new_bet

    hand.last_raise_size = (
        new_bet - previous_bet
    )

    hand.last_raiser = player

    player.acted_this_round = True

    return new_bet