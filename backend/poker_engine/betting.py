"""Betting rounds: action order, legal actions and action execution.

A betting round is driven one action at a time. ``hand.current_player`` is the
player expected to act; it is ``None`` once the round is complete.
"""

from .actions import (
    Action,
    LegalAction,
    all_in,
    call,
    check,
    fold,
    get_call_amount,
    get_maximum_raise_to,
    get_minimum_raise_size,
    get_minimum_raise_to,
    raise_bet,
)
from .constants import ActionType, BettingStructure, Street
from .history import record_action
from .models import ActionEvent, Hand, Player
from .showdown import resolve_by_fold


class IllegalActionError(ValueError):
    """Raised when a requested action is not legal in the current state."""


# Folding and checking never carry an amount: one shared immutable value each.
LEGAL_FOLD = LegalAction(type=ActionType.FOLD)
LEGAL_CHECK = LegalAction(type=ActionType.CHECK)


def get_first_to_act(hand: Hand) -> Player:
    """Return the seat where the action of the current street starts.

    Pre-flop the action starts left of the Big Blind (the Button heads-up).
    Post-flop it starts with the first seat left of the Button.
    """
    if hand.street != Street.PREFLOP:
        return hand.table.players_after(hand.table.dealer)[0]

    if hand.first_to_act is None:
        raise RuntimeError("first_to_act has not been assigned.")

    if hand.first_to_act not in hand.table.players:
        raise RuntimeError("first_to_act is not seated at the table.")

    return hand.first_to_act


def get_players_in_betting_order(hand: Hand) -> list[Player]:
    """Return the players able to act, in the action order of the street."""
    return [player for player in _seats_in_street_order(hand) if player.can_act]


def betting_round_can_continue(hand: Hand) -> bool:
    """Return True while a meaningful betting decision remains possible.

    There is nothing to decide when every remaining player is all-in, or when
    the only player with chips has already matched every opponent's bet.
    """
    active_players = hand.table.get_active_players()
    players_who_can_act = [player for player in active_players if not player.all_in]

    if len(active_players) < 2 or not players_who_can_act:
        return False

    if len(players_who_can_act) >= 2:
        return True

    lone_player = players_who_can_act[0]
    highest_opposing_bet = max(
        player.current_bet for player in active_players if player is not lone_player
    )

    return lone_player.current_bet < highest_opposing_bet


def is_betting_closed(hand: Hand) -> bool:
    """Return True once no more betting is possible for the rest of the hand.

    At least two players are still in the hand, and at most one of them can
    act and has nothing to call: every other player is all-in. The remaining
    streets are then dealt without any decision, and the players' cards can
    be shown.
    """
    if hand.finished:
        return False

    return len(hand.table.get_active_players()) >= 2 and not (
        betting_round_can_continue(hand)
    )


def needs_to_act(player: Player, hand: Hand) -> bool:
    """Return True if the player still owes a decision in this round."""
    if not player.can_act:
        return False

    return not player.acted_this_round or player.current_bet < hand.current_bet


def can_raise(player: Player, hand: Hand) -> bool:
    """Return True if the player may bet or raise.

    A player who already acted may only raise again when facing at least a
    full raise: a short all-in does not reopen the betting. Raising is also
    pointless, hence not offered, when no opponent is able to respond, and
    not allowed once the round has reached its cap of bets.
    """
    if player.stack <= get_call_amount(player=player, hand=hand):
        return False

    opponent_can_respond = any(
        other.can_act for other in hand.table.players if other is not player
    )

    if not opponent_can_respond:
        return False

    if hand.bet_cap is not None and hand.bets_this_street >= hand.bet_cap:
        return False

    if not player.acted_this_round:
        return True

    if hand.betting == BettingStructure.FIXED_LIMIT:
        return hand.full_bet > player.current_bet

    return hand.current_bet - player.current_bet >= get_minimum_raise_size(hand)


def get_legal_actions(player: Player, hand: Hand) -> tuple[LegalAction, ...]:
    """Return the actions currently available to a player."""
    call_amount = get_call_amount(player=player, hand=hand)

    actions = [LEGAL_FOLD]

    if call_amount == 0:
        actions.append(LEGAL_CHECK)
    else:
        actions.append(
            LegalAction(type=ActionType.CALL, amount=min(call_amount, player.stack))
        )

    if can_raise(player=player, hand=hand):
        minimum_raise_to = get_minimum_raise_to(hand)
        all_in_to = player.current_bet + player.stack
        # Pot Limit and Fixed Limit: a stack above the limit cannot all go in.
        limit = get_maximum_raise_to(player=player, hand=hand)
        maximum_raise_to = min(all_in_to, limit)

        if maximum_raise_to >= minimum_raise_to:
            actions.append(
                LegalAction(
                    type=ActionType.RAISE,
                    min_amount=minimum_raise_to,
                    max_amount=maximum_raise_to,
                )
            )

        if all_in_to <= limit:
            actions.append(LegalAction(type=ActionType.ALL_IN, amount=player.stack))

    return tuple(actions)


def get_current_legal_actions(hand: Hand) -> tuple[LegalAction, ...]:
    """Return the legal actions of ``hand.current_player``.

    The result is cached on the hand, so building a player's decision and
    executing it compute the legal actions only once. The cache is keyed by
    every value they depend on that can change during the street, plus the
    number of actions played, which changes with any other player's state.
    """
    player = hand.current_player

    if player is None:
        raise IllegalActionError("No player is expected to act.")

    state = (
        hand.street,
        len(hand.actions),
        hand.current_bet,
        hand.last_raise_size,
        hand.min_bet,
        player.stack,
        player.current_bet,
        player.acted_this_round,
    )
    cache = hand.legal_actions_cache

    if cache is not None and cache[0] is player and cache[1] == state:
        return cache[2]

    actions = get_legal_actions(player=player, hand=hand)
    hand.legal_actions_cache = (player, state, actions)

    return actions


def begin_betting_round(hand: Hand) -> None:
    """Give the action to the first player who has a decision to make."""
    hand.current_player = _find_next_to_act(
        hand=hand,
        seats=_seats_in_street_order(hand),
    )

    if hand.current_player is None:
        _record_betting_closed(hand)


def apply_action(hand: Hand, action: Action) -> ActionEvent:
    """Execute the action of the current player and move the action on.

    Raises IllegalActionError when the action is not legal. When every other
    player has folded, the pot is awarded and the hand is finished.

    An all-in is accepted in place of a call when the player's stack does not
    exceed the amount to call; it is then recorded as a call.
    """
    player = hand.current_player

    if hand.finished or player is None:
        raise IllegalActionError("No player is expected to act.")

    # Pushing a stack that does not exceed the amount to call is a call.
    if action.type == ActionType.ALL_IN and 0 < player.stack <= get_call_amount(
        player=player, hand=hand
    ):
        action = Action(type=ActionType.CALL)

    legal_action = next(
        (
            legal_action
            for legal_action in get_current_legal_actions(hand)
            if legal_action.type == action.type
        ),
        None,
    )

    if legal_action is None:
        raise IllegalActionError(f"{player.name} cannot {action.type} now.")

    bet_before = player.current_bet
    current_bet_before = hand.current_bet

    _execute(hand=hand, player=player, action=action, legal_action=legal_action)

    event = record_action(
        hand=hand,
        player=player,
        action=action.type,
        amount=player.current_bet - bet_before,
        bet_before=bet_before,
        bet_initiator=current_bet_before == 0 and hand.current_bet > 0,
    )

    hand.last_player_to_act = player

    active_players = hand.table.get_active_players()

    if len(active_players) == 1:
        resolve_by_fold(hand=hand, winner=active_players[0])
    else:
        hand.current_player = _find_next_to_act(
            hand=hand,
            seats=hand.table.players_after(player),
        )

        if hand.current_player is None:
            _record_betting_closed(hand)

    return event


def _record_betting_closed(hand: Hand) -> None:
    """Note the last action before the betting closed (once per hand)."""
    if hand.revealed_after_action is None and is_betting_closed(hand):
        hand.revealed_after_action = len(hand.actions)


def _execute(
    hand: Hand,
    player: Player,
    action: Action,
    legal_action: LegalAction,
) -> None:
    """Apply an action already known to be of a legal type."""
    match action.type:
        case ActionType.FOLD:
            fold(player)
        case ActionType.CHECK:
            check(player=player, hand=hand)
        case ActionType.CALL:
            call(player=player, hand=hand)
        case ActionType.ALL_IN:
            all_in(player=player, hand=hand)
        case ActionType.RAISE:
            raise_to = _validated_raise_amount(action, legal_action)
            raise_bet(player=player, hand=hand, raise_to=raise_to)


def _validated_raise_amount(action: Action, legal_action: LegalAction) -> int:
    """Return the requested "raise to" amount, or raise if it is not legal."""
    minimum = legal_action.min_amount
    maximum = legal_action.max_amount

    if action.amount is None or minimum is None or maximum is None:
        raise IllegalActionError("A raise requires an amount.")

    if not minimum <= action.amount <= maximum:
        raise IllegalActionError(
            f"Raise to {action.amount} is outside the legal range {minimum}-{maximum}."
        )

    return action.amount


def _seats_in_street_order(hand: Hand) -> list[Player]:
    """Return every seat, starting with the first to act on this street."""
    first = get_first_to_act(hand)

    return [first, *hand.table.players_after(first)[:-1]]


def _find_next_to_act(hand: Hand, seats: list[Player]) -> Player | None:
    """Return the first of ``seats`` owing a decision, or None if none does."""
    if not betting_round_can_continue(hand):
        return None

    return next(
        (player for player in seats if needs_to_act(player=player, hand=hand)),
        None,
    )
