"""Player actions and the chip movements they trigger."""

from dataclasses import dataclass

from .constants import ActionType, BettingStructure, Street
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
    hand.full_bet = amount
    hand.bets_this_street = 1

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


def get_fixed_limit_bet(hand: Hand) -> int:
    """Fixed Limit: the size of every bet and raise of the street.

    The small bet (the big blind) pre-flop and on the flop, the big bet
    (twice the big blind) on the turn and the river.
    """
    if hand.street in (Street.TURN, Street.RIVER):
        return 2 * hand.min_bet

    return hand.min_bet


def get_minimum_raise_to(hand: Hand) -> int:
    """Return the minimum legal "raise to" amount.

    Example: current bet 20, last raise 10 -> minimum raise to 30. In Fixed
    Limit a raise goes one bet above the last full bet: after a short all-in
    that is not a raise, the next player completes the bet.
    """
    if hand.betting == BettingStructure.FIXED_LIMIT:
        return hand.full_bet + get_fixed_limit_bet(hand)

    return hand.current_bet + get_minimum_raise_size(hand)


def get_maximum_raise_to(player: Player, hand: Hand) -> int:
    """Return the largest "raise to" the betting structure allows a player.

    No Limit: the whole stack. Pot Limit: the call, plus the pot after the
    call (pre-flop with blinds of 5/10, the first raise is to 35). Fixed
    Limit: the one raise allowed. The player's stack may be shorter.
    """
    match hand.betting:
        case BettingStructure.FIXED_LIMIT:
            return get_minimum_raise_to(hand)
        case BettingStructure.POT_LIMIT:
            call_amount = get_call_amount(player=player, hand=hand)
            return hand.current_bet + hand.pot + call_amount
        case _:
            return player.current_bet + player.stack


def counts_as_full_raise(hand: Hand, bet_to: int) -> bool:
    """Whether an all-in to ``bet_to`` is a full bet or raise.

    A full one reopens the betting and counts toward the cap. No Limit and
    Pot Limit: at least the minimum raise. Fixed Limit: at least half a bet
    above the last full bet (the half-bet rule).
    """
    if bet_to <= hand.current_bet:
        return False

    if hand.betting == BettingStructure.FIXED_LIMIT:
        return 2 * (bet_to - hand.full_bet) >= get_fixed_limit_bet(hand)

    return bet_to >= get_minimum_raise_to(hand)


def _record_full_raise(hand: Hand, player: Player, previous_bet: int) -> None:
    hand.last_raise_size = player.current_bet - previous_bet
    hand.last_raiser = player
    hand.full_bet = player.current_bet
    hand.bets_this_street += 1


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

    maximum_raise_to = get_maximum_raise_to(player=player, hand=hand)

    if raise_to > maximum_raise_to:
        raise ValueError(f"Maximum raise is to {maximum_raise_to}.")

    previous_bet = hand.current_bet

    put_chips_in_pot(player=player, hand=hand, amount=amount_to_add)

    hand.current_bet = player.current_bet
    _record_full_raise(hand=hand, player=player, previous_bet=previous_bet)
    player.acted_this_round = True

    return player.current_bet


def all_in(player: Player, hand: Hand) -> int:
    """Move the player's entire remaining stack into the pot.

    An all-in above the current bet always becomes the bet to call. It only
    counts as a raise (new minimum raise size, new last raiser) when it is a
    full raise (``counts_as_full_raise``); a shorter all-in does not reopen
    the betting.
    """
    if player.stack <= 0:
        raise ValueError("Player has no chips available.")

    previous_bet = hand.current_bet
    full_raise = counts_as_full_raise(hand, player.current_bet + player.stack)

    actual_amount = put_chips_in_pot(player=player, hand=hand, amount=player.stack)

    if player.current_bet > previous_bet:
        hand.current_bet = player.current_bet

        if full_raise:
            _record_full_raise(hand=hand, player=player, previous_bet=previous_bet)

    player.acted_this_round = True

    return actual_amount
