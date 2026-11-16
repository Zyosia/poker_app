"""Player actions and the chip movements they trigger."""

from dataclasses import dataclass

from .constants import ActionType
from .models import Hand, Player


@dataclass(frozen=True)
class Action:
    """An action requested by a player.

    ``amount`` is only used by a raise: it is the total bet the player raises
    to on the current street.
    """

    type: ActionType
    amount: int | None = None


@dataclass(frozen=True)
class LegalAction:
    """An action currently available to a player.

    ``amount`` is the number of chips a call or an all-in adds to the pot.
    ``min_amount`` and ``max_amount`` bound the "raise to" total of a raise.
    """

    type: ActionType
    amount: int | None = None
    min_amount: int | None = None
    max_amount: int | None = None


def put_chips_in_pot(player: Player, hand: Hand, amount: int) -> int:
    """Move chips from a player's stack into the pot.

    The amount is capped at the player's remaining stack, which puts the
    player all-in. Returns the number of chips actually moved.
    """
    if amount < 0:
        raise ValueError("Chip amount cannot be negative.")

    actual_amount = min(amount, player.stack)

    player.stack -= actual_amount
    player.current_bet += actual_amount
    player.total_contribution += actual_amount
    hand.pot += actual_amount

    if player.stack == 0:
        player.all_in = True

    return actual_amount


def post_ante(player: Player, hand: Hand, amount: int, for_table: bool) -> int:
    """Post an ante: dead money, outside the player's bet on the street.

    The chips go into the pot but not into ``current_bet``, so they count
    neither toward the amount to call nor toward raises. A player who cannot
    cover the ante posts what they have and is all-in.

    A classic ante (``for_table`` False) is part of the player's total
    contribution: a player all-in for a short ante only wins what the others
    matched of it. A big-blind ante (``for_table`` True) is paid for the whole
    table: it goes into the main pot as ``hand.dead_money``.
    """
    if amount < 0:
        raise ValueError("Chip amount cannot be negative.")

    actual_amount = min(amount, player.stack)

    player.stack -= actual_amount
    hand.pot += actual_amount

    if for_table:
        hand.dead_money += actual_amount
    else:
        player.total_contribution += actual_amount

    if player.stack == 0:
        player.all_in = True

    return actual_amount


def post_small_blind(player: Player, hand: Hand, amount: int) -> int:
    """Post the small blind."""
    return put_chips_in_pot(player=player, hand=hand, amount=amount)


def post_big_blind(player: Player, hand: Hand, amount: int) -> int:
    """Post the big blind.

    The bet to call is the full big blind even when the player posting it is
    all-in for less.
    """
    posted_amount = put_chips_in_pot(player=player, hand=hand, amount=amount)

    hand.current_bet = amount
    hand.last_raise_size = amount

    return posted_amount


def fold(player: Player) -> None:
    """Fold the player's hand."""
    player.folded = True
    player.acted_this_round = True


def can_check(player: Player, hand: Hand) -> bool:
    """Return True if the player can check."""
    return player.current_bet >= hand.current_bet


def check(player: Player, hand: Hand) -> None:
    """Check when no additional chips are required."""
    if not can_check(player=player, hand=hand):
        raise ValueError("Cannot check. You must call, raise or fold.")

    player.acted_this_round = True


def get_call_amount(player: Player, hand: Hand) -> int:
    """Return the amount required to call."""
    return max(0, hand.current_bet - player.current_bet)


def call(player: Player, hand: Hand) -> int:
    """Call the current bet, going all-in when the stack is too short."""
    actual_amount = put_chips_in_pot(
        player=player,
        hand=hand,
        amount=get_call_amount(player=player, hand=hand),
    )

    player.acted_this_round = True

    return actual_amount


def get_minimum_raise_size(hand: Hand) -> int:
    """Return the smallest increment that counts as a full bet or raise."""
    return max(hand.last_raise_size, hand.min_bet)


def get_minimum_raise_to(hand: Hand) -> int:
    """Return the minimum legal "raise to" amount.

    Example: current bet 20, last raise 10 -> minimum raise to 30.
    """
    return hand.current_bet + get_minimum_raise_size(hand)


def raise_bet(player: Player, hand: Hand, raise_to: int) -> int:
    """Bet or raise to an absolute amount on the current street.

    Example: the current bet is 20, the player already invested 20 and raises
    to 40, so 20 chips are added. Returns the new current bet.
    """
    if raise_to <= hand.current_bet:
        raise ValueError("Raise must be greater than the current bet.")

    minimum_raise_to = get_minimum_raise_to(hand)

    if raise_to < minimum_raise_to:
        raise ValueError(f"Minimum raise is to {minimum_raise_to}.")

    amount_to_add = raise_to - player.current_bet

    if amount_to_add > player.stack:
        raise ValueError("Not enough chips for this raise.")

    previous_bet = hand.current_bet

    put_chips_in_pot(player=player, hand=hand, amount=amount_to_add)

    hand.current_bet = player.current_bet
    hand.last_raise_size = player.current_bet - previous_bet
    hand.last_raiser = player
    player.acted_this_round = True

    return player.current_bet


def all_in(player: Player, hand: Hand) -> int:
    """Move the player's entire remaining stack into the pot.

    An all-in above the current bet always becomes the bet to call. It only
    counts as a raise (new minimum raise size, new last raiser) when it is at
    least a full raise; a shorter all-in does not reopen the betting.
    """
    if player.stack <= 0:
        raise ValueError("Player has no chips available.")

    previous_bet = hand.current_bet
    minimum_raise_to = get_minimum_raise_to(hand)

    actual_amount = put_chips_in_pot(player=player, hand=hand, amount=player.stack)

    if player.current_bet > previous_bet:
        hand.current_bet = player.current_bet

        if player.current_bet >= minimum_raise_to:
            hand.last_raise_size = player.current_bet - previous_bet
            hand.last_raiser = player

    player.acted_this_round = True

    return actual_amount
