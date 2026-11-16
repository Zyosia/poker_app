"""Stack-aware tournament play of the heuristic bot.

In a cash game a bot reloads; in a tournament busting ends its game, and the
blinds keep rising. So in a tournament the bot measures its **effective
stack** (the smaller of its stack and the biggest opponent stack still in the
hand, bets included) in big blinds, and pre-flop:

- **Push/fold** (at most ``profile.push_fold_big_blinds``): it only shoves or
  folds (checks when free), using the ranges of ``push_fold``. It never
  makes a small raise.
- **Short stack** (up to ``profile.short_stack_big_blinds``): it opens
  smaller (2.2 big blinds plus one per limper), re-raises all-in instead of
  making small re-raises, and flat-calls a raise only with a strong hand.

At any depth, a bet or raise that would put 40% or more of its stack in the
pot becomes an all-in. Deeper stacks play the usual heuristic. Cash games
never use this module: their behaviour is unchanged.
"""

from collections.abc import Callable

from backend.application.controllers import DecisionContext
from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.constants import ActionType, Position, Street

from .profiles import BotProfile
from .push_fold import call_shove_percent, in_top_percent, open_shove_percent

OPEN_RAISE_BIG_BLINDS = 2.2
COMMITMENT_SHARE = 0.4
"""Putting at least this share of the stack in the pot commits to it."""


def effective_big_blinds(context: DecisionContext) -> float:
    """Effective stack in big blinds, bets of this street included."""
    me = context.player
    own = me.stack + me.current_bet
    opponents = [
        player.stack + player.current_bet
        for player in context.players
        if player.name != me.name and not player.folded and player.position
    ]

    return min(own, max(opponents, default=own)) / context.big_blind


def tournament_action(
    context: DecisionContext,
    profile: BotProfile,
    preflop_strength: float,
    heuristic: Callable[[], Action],
) -> Action:
    """The decision of a bot in a tournament.

    ``heuristic`` returns the usual decision; it is only called when the
    stack is deep enough for it to matter.
    """
    legal = {action.type: action for action in context.legal_actions}

    if context.street == Street.PREFLOP:
        depth = effective_big_blinds(context)

        if depth <= profile.push_fold_big_blinds:
            return _push_or_fold(context, profile, depth, legal)

        if depth <= profile.short_stack_big_blinds:
            return _short_stack_preflop(
                context, profile, depth, legal, preflop_strength, heuristic
            )

    return _committed(heuristic(), context, legal)


def _push_or_fold(
    context: DecisionContext,
    profile: BotProfile,
    depth: float,
    legal: dict[ActionType, LegalAction],
) -> Action:
    if _facing_raise(context):
        percent = _call_percent(context, depth) * profile.call_range_scale
    else:
        percent = open_shove_percent(_range_position(context), depth)
        percent *= profile.shove_range_scale

    if in_top_percent(context.hole_cards, percent):
        return _shove(legal)

    return _check_or_fold(legal)


def _short_stack_preflop(
    context: DecisionContext,
    profile: BotProfile,
    depth: float,
    legal: dict[ActionType, LegalAction],
    preflop_strength: float,
    heuristic: Callable[[], Action],
) -> Action:
    if _facing_raise(context):
        # Re-shove the hands that would call a shove at this depth.
        percent = _call_percent(context, depth) * profile.shove_range_scale

        if in_top_percent(context.hole_cards, percent):
            return _shove(legal)

        action = heuristic()

        if action.type == ActionType.RAISE:
            return _shove(legal)

        if action.type == ActionType.CALL and preflop_strength < profile.call_threshold:
            return _check_or_fold(legal)

        return action

    action = heuristic()

    if action.type == ActionType.RAISE:
        return _committed(_small_open(context, legal), context, legal)

    return action


def _small_open(
    context: DecisionContext, legal: dict[ActionType, LegalAction]
) -> Action:
    raise_action = legal[ActionType.RAISE]
    assert raise_action.min_amount is not None and raise_action.max_amount is not None
    limpers = sum(
        1
        for event in context.actions
        if event.street == Street.PREFLOP and event.action == ActionType.CALL
    )
    target = round((OPEN_RAISE_BIG_BLINDS + limpers) * context.big_blind)
    amount = min(max(target, raise_action.min_amount), raise_action.max_amount)

    return Action(type=ActionType.RAISE, amount=amount)


def _committed(
    action: Action, context: DecisionContext, legal: dict[ActionType, LegalAction]
) -> Action:
    """Turn a raise putting most of the stack in into an all-in."""
    if action.type != ActionType.RAISE or action.amount is None:
        return action

    added = action.amount - context.player.current_bet

    if added >= COMMITMENT_SHARE * context.player.stack and ActionType.ALL_IN in legal:
        return Action(type=ActionType.ALL_IN)

    return action


def _facing_raise(context: DecisionContext) -> bool:
    return context.current_bet > context.big_blind


def _call_percent(context: DecisionContext, depth: float) -> float:
    """Range calling (or re-shoving over) the aggression of the street."""
    callers = 0
    raised = False

    for event in context.actions:
        if event.street != Street.PREFLOP:
            continue

        if event.action in (ActionType.RAISE, ActionType.ALL_IN):
            callers += 1 if raised else 0
            raised = True
        elif raised and event.action == ActionType.CALL:
            callers += 1

    is_big_blind = context.player.position == Position.BB

    return call_shove_percent(is_big_blind, depth, multiway=callers > 0)


def _range_position(context: DecisionContext) -> Position:
    """Position for the open-shove ranges; heads-up, the button is the SB."""
    dealt_in = sum(1 for player in context.players if player.position is not None)
    position = context.player.position

    if position is None:
        raise ValueError("A player dealt in always has a position.")

    if dealt_in == 2 and position == Position.BTN:
        return Position.SB

    return position


def _shove(legal: dict[ActionType, LegalAction]) -> Action:
    for action_type in (ActionType.ALL_IN, ActionType.CALL, ActionType.CHECK):
        if action_type in legal:
            return Action(type=action_type)

    return Action(type=ActionType.FOLD)


def _check_or_fold(legal: dict[ActionType, LegalAction]) -> Action:
    if ActionType.CHECK in legal:
        return Action(type=ActionType.CHECK)

    return Action(type=ActionType.FOLD)
