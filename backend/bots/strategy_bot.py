"""The strategy bots of V2.0: Shark and Adaptive.

Both play the same way; the adaptive bot also learns its opponents.

**Pre-flop**, by charts (``preflop_charts``): it opens a range that depends
on how many players are still to act, re-raises or calls a raise depending on
how wide the raiser's range is, and only continues against a re-raise with
strong hands.

**In tournaments**, it measures its stack with the **M ratio** (stack
divided by the cost of a round of blinds and antes):

- at ``PUSH_FOLD_M`` or less, it shoves or folds (the ``push_fold`` ranges,
  for the stack in big blinds a round of blinds would cost without antes);
- up to ``SHORT_M``, it opens smaller and re-raises all-in or folds;
- heads-up, or three-handed (button, small blind, big blind), with
  ``SOLVED_BIG_BLINDS`` or less, it plays the push/fold equilibrium solved
  by CFR for the hand's antes (``push_fold_solutions``, V2.x).

**After the flop**, it estimates each opponent's range from their actions,
deals a few hundred Monte Carlo showdowns against those ranges, and picks
the action with the best **expected value** (in chips, from now on):

- fold: 0; check: equity × pot; call: equity × (pot + call) − call;
- bet or raise (half pot, three quarters, pot, all-in): each opponent
  calls with the hands strong enough for the price they are offered, folds
  the others. A deal where everyone folds wins the pot; otherwise the bot
  wins its share against the callers of the pot they build, minus its bet.

**The adaptive bot** reads the live statistics of each opponent
(``StatsBook``): it widens or narrows their ranges with how often they play
and raise, expects more bluffs from aggressive players, bluffs more against
players who fold to bets and less against calling stations, and steals the
blinds more often from tight players.
"""

import random
from dataclasses import dataclass, field
from functools import cache

from backend.application.controllers import (
    DecisionContext,
    GameFormat,
    PlayerController,
    PlayerView,
)
from backend.application.ranges import HandRange
from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.constants import ActionType, Position, Street
from backend.poker_engine.models import ActionEvent

from .monte_carlo import Showdown, deal_showdowns, equity, share_against
from .opponent_model import (
    AGGRESSIVE,
    BLIND_POSTS,
    PRIOR,
    OpponentRange,
    PlayerTendencies,
    StatsBook,
    starting_range,
)
from .preflop_charts import (
    CALL_THREE_BET,
    FOUR_BET,
    call_percent,
    hand_percent,
    open_percent,
    open_range,
    players_behind,
    three_bet_percent,
)
from .push_fold import call_shove_percent, hand_class, open_shove_percent
from .push_fold_solutions import HEADS_UP_RANGES, THREE_HANDED_RANGES
from .three_handed_solver import Spot

SHOWDOWNS = 200
"""Monte Carlo deals per decision after the flop, at most."""
FIRST_SHOWDOWNS = 100
"""Deals first; the rest only when the decision is close (V2.x: faster)."""
CLEAR_MARGIN = 0.1
"""A decision is clear when the best option beats the next one by this
share of the pot: the second half of the deals would not change it."""
BET_FRACTIONS = (0.5, 0.75, 1.0)
"""Bet sizes tried, as fractions of the pot after calling."""
CALL_MARGIN = 0.05
"""An opponent calls with a strength at least the share of the pot they
pay, plus this margin."""
FOLD_SHIFT = 0.5
"""How much the adaptive bot moves that threshold per point of an
opponent's fold-to-bet frequency above (or below) the typical one."""
MAX_SHOVE_SPR = 1.5
"""Stack-to-pot ratio up to which an all-in is considered after the flop."""
COMMITMENT_SHARE = 0.4
"""Putting this share of the stack in commits to it: an all-in instead."""

OPEN_BIG_BLINDS = 2.5
SHORT_OPEN_BIG_BLINDS = 2.2
ISOLATION_BIG_BLINDS = 3.0
THREE_BET_FACTOR = 3.0
FOUR_BET_FACTOR = 2.3
MAX_FLAT_SHARE = 0.15
"""A raise costing more than this share of the stack is not flat-called."""
MAX_THREE_BET_CALL_SHARE = 0.1
BIG_BLIND_RAISE_PERCENT = 8.0
"""The big blind raises limpers with about the strongest 8% of hands."""

PUSH_FOLD_M = 7.0
SHORT_M = 15.0
BIG_BLINDS_PER_M = 1.5
"""A round of blinds without antes costs 1.5 big blinds."""
SOLVED_BIG_BLINDS = 20
"""Up to this effective stack, two or three players play the solved ranges."""

STEAL_POSITIONS_BEHIND = 3
"""Cutoff, button and small blind: the seats that steal the blinds."""
TIGHT_VPIP = 0.22
LOOSE_VPIP = 0.45
"""The adaptive bot isolates players who play this share of hands or more."""
LOOSE_PFR = 0.35
"""A player raising this often re-raises light: answered like an open."""
LOOSE_WIDENING = 2
"""Players behind counted fewer, to open wider, when loose ones are left."""
STREET_CARDS = {Street.FLOP: 3, Street.TURN: 4, Street.RIVER: 5}
FULL_RING_SHOVE_POSITIONS = {
    Position.UTG1: Position.UTG,
    Position.UTG2: Position.UTG,
    Position.LJ: Position.UTG,
}


@dataclass
class HandState:
    """What the bot has worked out about the current hand."""

    key: tuple[object, ...]
    ranges: dict[str, OpponentRange] = field(default_factory=dict)
    read: int = 0
    """Actions already used to narrow the ranges."""


class StrategyBot(PlayerController):
    """Pre-flop charts, M ratio, ranges, Monte Carlo equity and EV."""

    def __init__(
        self, rng: random.Random | None = None, adaptive: bool = False
    ) -> None:
        self._rng = rng or random.Random()
        self.adaptive = adaptive
        self.stats = StatsBook()
        self._hand: HandState | None = None

    def observe_hand(self, actions: tuple[ActionEvent, ...]) -> None:
        if self.adaptive:
            self.stats.record_hand(actions)

    def tendencies(self, name: str) -> PlayerTendencies:
        return self.stats.tendencies(name) if self.adaptive else PRIOR

    def choose_action(self, context: DecisionContext) -> Action:
        legal = {action.type: action for action in context.legal_actions}
        state = self._hand_state(context)

        if context.street == Street.PREFLOP:
            action = self._preflop(context, legal)
        else:
            action = self._postflop(context, legal, state)

        return self._committed(action, context, legal)

    # --- Pre-flop ------------------------------------------------------------------

    def _preflop(
        self, context: DecisionContext, legal: dict[ActionType, LegalAction]
    ) -> Action:
        dealt_in = tuple(p.position for p in context.players if p.position is not None)
        heads_up = len(dealt_in) == 2
        depth = effective_big_blinds(context)

        if context.game_format == GameFormat.TOURNAMENT:
            if heads_up and depth <= SOLVED_BIG_BLINDS:
                return self._heads_up_push_fold(context, legal, depth)

            if len(dealt_in) == 3 and depth <= SOLVED_BIG_BLINDS:
                return self._three_handed_push_fold(context, legal, depth)

            m = m_ratio(context)

            if m <= PUSH_FOLD_M:
                return self._push_or_fold(context, legal, m * BIG_BLINDS_PER_M)

        short = (
            context.game_format == GameFormat.TOURNAMENT and m_ratio(context) <= SHORT_M
        )
        raises = [
            e
            for e in context.actions
            if e.street == Street.PREFLOP and e.action in AGGRESSIVE
        ]
        me = context.player
        assert me.position is not None
        behind = players_behind(me.position, dealt_in)

        if not raises:
            return self._unopened(context, legal, behind, heads_up, short)

        if len(raises) == 1:
            return self._facing_open(context, legal, raises[0], dealt_in, short)

        if self.adaptive and self.tendencies(raises[-1].player).pfr >= LOOSE_PFR:
            # A loose player's re-raise is no stronger than another's open.
            return self._facing_open(context, legal, raises[-1], dealt_in, short)

        hole = hand_class(context.hole_cards)

        if len(raises) == 2 and hole in FOUR_BET.labels:
            return self._raise_to(context, legal, context.current_bet * FOUR_BET_FACTOR)

        if len(raises) >= 3 and hole in FOUR_BET.labels:
            return _shove(legal)

        price = _call_amount(legal)
        opened = raises[0].player == me.name

        if (
            len(raises) == 2
            and opened
            and not short
            and hole in CALL_THREE_BET.labels
            and price <= MAX_THREE_BET_CALL_SHARE * (me.stack + me.current_bet)
        ):
            return Action(type=ActionType.CALL)

        return _check_or_fold(legal)

    def _unopened(
        self,
        context: DecisionContext,
        legal: dict[ActionType, LegalAction],
        behind: int,
        heads_up: bool,
        short: bool,
    ) -> Action:
        limpers = sum(
            1
            for e in context.actions
            if e.street == Street.PREFLOP and e.action == ActionType.CALL
        )
        big_blind = context.big_blind

        if ActionType.CHECK in legal:  # The big blind, limped to.
            if hand_percent(context.hole_cards) < BIG_BLIND_RAISE_PERCENT:
                return self._raise_to(
                    context, legal, (ISOLATION_BIG_BLINDS + limpers) * big_blind
                )
            return Action(type=ActionType.CHECK)

        limping = {
            e.player
            for e in context.actions
            if e.street == Street.PREFLOP and e.action == ActionType.CALL
        }
        loose_limpers = sum(1 for name in limping if self._is_loose(name))
        # A limper narrows the range, except a loose one: they are isolated.
        widened = behind + 2 * (limpers - loose_limpers)

        if self.adaptive and (loose_limpers or self._loose_behind(context)):
            widened -= LOOSE_WIDENING

        if (
            self.adaptive
            and not limpers
            and behind <= STEAL_POSITIONS_BEHIND
            and self._tight_behind(context)
        ):
            widened -= 1  # The blinds rarely defend: steal more.

        if (
            hand_class(context.hole_cards)
            not in open_range(max(widened, 1), heads_up).labels
        ):
            return _check_or_fold(legal)

        size = SHORT_OPEN_BIG_BLINDS if short else OPEN_BIG_BLINDS

        return self._raise_to(context, legal, (size + limpers) * big_blind)

    def _is_loose(self, name: str) -> bool:
        return self.adaptive and self.tendencies(name).vpip >= LOOSE_VPIP

    def _loose_behind(self, context: DecisionContext) -> bool:
        acted = {e.player for e in context.actions if e.action not in BLIND_POSTS}

        return any(
            self._is_loose(p.name)
            for p in context.players
            if p.position is not None
            and p.name != context.player.name
            and p.name not in acted
        )

    def _tight_behind(self, context: DecisionContext) -> bool:
        acted = {e.player for e in context.actions if e.action not in BLIND_POSTS}
        others = [
            p
            for p in context.players
            if p.position is not None
            and p.name != context.player.name
            and p.name not in acted
        ]

        return bool(others) and all(
            self.tendencies(p.name).vpip < TIGHT_VPIP for p in others
        )

    def _facing_open(
        self,
        context: DecisionContext,
        legal: dict[ActionType, LegalAction],
        opener_event: ActionEvent,
        dealt_in: tuple[Position, ...],
        short: bool,
    ) -> Action:
        me = context.player
        opener = _player(context, opener_event.player)
        stack = me.stack + me.current_bet
        price = _call_amount(legal)
        percent = hand_percent(context.hole_cards)
        is_big_blind = me.position == Position.BB

        # An all-in, or a raise that commits us: call or fold.
        if opener.all_in or price >= COMMITMENT_SHARE * me.stack:
            depth = effective_big_blinds(context)
            callers = _callers_after(context, opener_event)

            threshold = call_shove_percent(is_big_blind, depth, multiway=callers > 0)

            if self.adaptive:
                # A loose shover shoves more hands: call them wider.
                looseness = self.tendencies(opener.name).pfr / PRIOR.pfr
                threshold = min(threshold * max(1.0, looseness), 100.0)

            if percent < threshold:
                if ActionType.CALL in legal:
                    return Action(type=ActionType.CALL)
                return _shove(legal)

            return _check_or_fold(legal)

        opener_range = self._opening_percent(opener, dealt_in)
        callers = _callers_after(context, opener_event)

        if percent < three_bet_percent(opener_range):
            target = context.current_bet * (THREE_BET_FACTOR + callers)
            return _shove(legal) if short else self._raise_to(context, legal, target)

        heads_up = len(dealt_in) == 2
        can_flat = (
            not short
            and (me.position != Position.SB or heads_up)
            and price <= MAX_FLAT_SHARE * stack
        )

        if can_flat and percent < call_percent(opener_range, is_big_blind):
            return Action(type=ActionType.CALL)

        return _check_or_fold(legal)

    def _opening_percent(
        self, opener: PlayerView, dealt_in: tuple[Position, ...]
    ) -> float:
        """How wide a player opens from their seat (percent of hands)."""
        assert opener.position is not None
        behind = players_behind(opener.position, dealt_in)
        percent = open_percent(behind, len(dealt_in) == 2)

        if self.adaptive:
            percent *= self.tendencies(opener.name).pfr / PRIOR.pfr

        return min(max(percent, 2.0), 100.0)

    # --- Short stacks (tournaments) ----------------------------------------------

    def _push_or_fold(
        self,
        context: DecisionContext,
        legal: dict[ActionType, LegalAction],
        depth: float,
    ) -> Action:
        percent = hand_percent(context.hole_cards)
        raised = [
            e
            for e in context.actions
            if e.street == Street.PREFLOP and e.action in AGGRESSIVE
        ]

        if raised:
            callers = _callers_after(context, raised[0]) + len(raised) - 1
            is_big_blind = context.player.position == Position.BB
            threshold = call_shove_percent(is_big_blind, depth, multiway=callers > 0)
        else:
            threshold = open_shove_percent(_shove_position(context), depth)

        if percent < threshold:
            return _shove(legal)

        return _check_or_fold(legal)

    def _heads_up_push_fold(
        self,
        context: DecisionContext,
        legal: dict[ActionType, LegalAction],
        depth: float,
    ) -> Action:
        solutions = HEADS_UP_RANGES[ante_kind(context)]
        push, call = solutions[_nearest(solutions, depth)]
        hole = hand_class(context.hole_cards)
        facing = context.current_bet > context.player.current_bet

        if context.player.position == Position.BB and (
            facing or ActionType.CHECK in legal
        ):
            # Facing a shove (or any raise), or a limp: the calling range goes all-in.
            if hole in _range(call):
                return _shove(legal)
            return _check_or_fold(legal)

        if hole in _range(push):
            return _shove(legal)

        return _check_or_fold(legal)

    def _three_handed_push_fold(
        self,
        context: DecisionContext,
        legal: dict[ActionType, LegalAction],
        depth: float,
    ) -> Action:
        """The solved three-handed ranges; any raise counts as a shove, a
        limp as a fold (the solution has no small bets)."""
        solutions = THREE_HANDED_RANGES[ante_kind(context)]
        ranges = solutions[_nearest(solutions, depth)]
        raisers = {
            e.position
            for e in context.actions
            if e.street == Street.PREFLOP and e.action in AGGRESSIVE
        }
        callers = {
            e.position
            for e in context.actions
            if e.street == Street.PREFLOP and e.action == ActionType.CALL
        }
        position = context.player.position
        button_in = Position.BTN in raisers
        small_in = Position.SB in raisers or (button_in and Position.SB in callers)

        if position == Position.BTN:
            spot = Spot.BUTTON_SHOVES
        elif position == Position.SB:
            spot = Spot.SMALL_BLIND_CALLS if button_in else Spot.SMALL_BLIND_SHOVES
        elif button_in and small_in:
            spot = Spot.BIG_BLIND_CALLS_BOTH
        elif button_in:
            spot = Spot.BIG_BLIND_CALLS_BUTTON
        else:
            spot = Spot.BIG_BLIND_CALLS_SMALL_BLIND

        if hand_class(context.hole_cards) in _range(ranges[spot]):
            return _shove(legal)

        return _check_or_fold(legal)

    # --- After the flop ----------------------------------------------------------

    def _postflop(
        self,
        context: DecisionContext,
        legal: dict[ActionType, LegalAction],
        state: HandState,
    ) -> Action:
        opponents = [
            p
            for p in context.players
            if p.position is not None and not p.folded and p.name != context.player.name
        ]

        if not opponents:
            return _check_or_fold(legal)

        self._update_ranges(context, state, opponents)
        board = context.community_cards
        ranges = [state.ranges[p.name] for p in opponents]
        strengths = [r.strengths(board) for r in ranges]
        showdowns = deal_showdowns(
            context.hole_cards, board, ranges, strengths, FIRST_SHOWDOWNS, self._rng
        )

        if not showdowns:
            return _check_or_fold(legal)

        options = self._options(context, legal, opponents, showdowns)

        if _margin(options) < CLEAR_MARGIN * context.pot:
            showdowns += deal_showdowns(
                context.hole_cards,
                board,
                ranges,
                strengths,
                SHOWDOWNS - FIRST_SHOWDOWNS,
                self._rng,
            )
            options = self._options(context, legal, opponents, showdowns)

        # Ties go to the most passive option, listed first.
        return max(options, key=lambda option: option[0])[1]

    def _options(
        self,
        context: DecisionContext,
        legal: dict[ActionType, LegalAction],
        opponents: list[PlayerView],
        showdowns: list[Showdown],
    ) -> list[tuple[float, Action]]:
        """The expected value of every option, the passive ones first."""
        pot = context.pot
        share = equity(showdowns)
        options: list[tuple[float, Action]] = []

        if ActionType.CHECK in legal:
            options.append((share * pot, Action(type=ActionType.CHECK)))
        else:
            options.append((0.0, Action(type=ActionType.FOLD)))

        call = legal.get(ActionType.CALL)

        if call is not None and call.amount is not None:
            options.append(
                (
                    share * (pot + call.amount) - call.amount,
                    Action(type=ActionType.CALL),
                )
            )

        for target in self._bet_targets(context, legal):
            value = self._bet_value(context, opponents, showdowns, target)
            options.append((value, self._raise_action(context, legal, target)))

        return options

    def _bet_targets(
        self, context: DecisionContext, legal: dict[ActionType, LegalAction]
    ) -> list[int]:
        me = context.player
        all_in = me.stack + me.current_bet
        raise_action = legal.get(ActionType.RAISE)
        targets: set[int] = set()

        if raise_action is not None:
            assert (
                raise_action.min_amount is not None
                and raise_action.max_amount is not None
            )
            after_call = context.pot + context.current_bet - me.current_bet

            for fraction in BET_FRACTIONS:
                target = context.current_bet + int(fraction * after_call)
                targets.add(
                    min(max(target, raise_action.min_amount), raise_action.max_amount)
                )

        # An all-in only when the stack is small next to the pot (or the only
        # raise left): opponents call big shoves more than prices suggest.
        shallow = me.stack <= MAX_SHOVE_SPR * context.pot or raise_action is None

        if ActionType.ALL_IN in legal and all_in > context.current_bet and shallow:
            targets.add(all_in)

        return sorted(targets)

    def _bet_value(
        self,
        context: DecisionContext,
        opponents: list[PlayerView],
        showdowns: list[Showdown],
        target: int,
    ) -> float:
        """Expected chips of betting (or raising) to ``target``."""
        me = context.player
        pot = context.pot
        reachable = max(o.stack + o.current_bet for o in opponents)
        added = min(target, reachable) - me.current_bet
        calls: list[int] = []
        thresholds: list[float] = []

        for opponent in opponents:
            pays = max(
                0,
                min(target, opponent.stack + opponent.current_bet)
                - opponent.current_bet,
            )
            calls.append(pays)

            if opponent.all_in or pays == 0:
                thresholds.append(-1.0)  # Already in: they cannot fold.
                continue

            price = pays / (pot + added + pays)
            shift = (
                self.tendencies(opponent.name).fold_to_bet - PRIOR.fold_to_bet
            ) * FOLD_SHIFT
            thresholds.append(price + CALL_MARGIN + shift)

        total = 0.0

        for showdown in showdowns:
            continuing = [
                i
                for i, (_, strength) in enumerate(showdown.opponents)
                if strength >= thresholds[i]
            ]

            if not continuing:
                total += pot
                continue

            called_pot = pot + added + sum(calls[i] for i in continuing)
            total += share_against(showdown, continuing) * called_pot - added

        return total / len(showdowns)

    def _update_ranges(
        self,
        context: DecisionContext,
        state: HandState,
        opponents: list[PlayerView],
    ) -> None:
        """Build the ranges at the first decision after the flop, then
        narrow them with every new action."""
        board = context.community_cards
        dealt_in = tuple(p.position for p in context.players if p.position is not None)

        if not state.ranges:
            preflop = [e for e in context.actions if e.street == Street.PREFLOP]
            dead = {*context.hole_cards, *board}

            for opponent in context.players:
                if opponent.position is None or opponent.name == context.player.name:
                    continue

                tendencies = self.tendencies(opponent.name)
                hands = starting_range(
                    preflop,
                    opponent.name,
                    self._opening_percent(opponent, dealt_in),
                    tendencies.vpip * 100,
                )
                state.ranges[opponent.name] = OpponentRange.from_starting_hands(
                    hands or {"AA": 1.0}, dead, self._rng
                )

            state.read = len(preflop)

        dead = {*context.hole_cards, *board}

        for opponent_range in state.ranges.values():
            opponent_range.remove(dead)

        for event in context.actions[state.read :]:
            opponent_range = state.ranges.get(event.player)

            if opponent_range is not None and event.street in STREET_CARDS:
                street_board = board[: STREET_CARDS[event.street]]
                opponent_range.narrow(
                    event.action, street_board, self.tendencies(event.player)
                )

        state.read = len(context.actions)

    # --- Helpers -----------------------------------------------------------------

    def _hand_state(self, context: DecisionContext) -> HandState:
        first = context.actions[0] if context.actions else None
        key = (context.hole_cards, first)
        state = self._hand

        if state is None or state.key != key or state.read > len(context.actions):
            state = HandState(key=key)
            self._hand = state

        return state

    def _raise_to(
        self,
        context: DecisionContext,
        legal: dict[ActionType, LegalAction],
        target: float,
    ) -> Action:
        return self._raise_action(context, legal, round(target))

    @staticmethod
    def _raise_action(
        context: DecisionContext, legal: dict[ActionType, LegalAction], target: int
    ) -> Action:
        """A raise to ``target`` within the legal amounts, or an all-in."""
        me = context.player
        raise_action = legal.get(ActionType.RAISE)

        if target >= me.stack + me.current_bet or raise_action is None:
            if ActionType.ALL_IN in legal:
                return Action(type=ActionType.ALL_IN)
            return (
                Action(type=ActionType.CALL)
                if ActionType.CALL in legal
                else _check_or_fold(legal)
            )

        assert (
            raise_action.min_amount is not None and raise_action.max_amount is not None
        )
        amount = min(max(target, raise_action.min_amount), raise_action.max_amount)

        return Action(type=ActionType.RAISE, amount=amount)

    @staticmethod
    def _committed(
        action: Action, context: DecisionContext, legal: dict[ActionType, LegalAction]
    ) -> Action:
        """A raise putting most of the stack in becomes an all-in."""
        if action.type != ActionType.RAISE or action.amount is None:
            return action

        added = action.amount - context.player.current_bet

        if (
            added >= COMMITMENT_SHARE * context.player.stack
            and ActionType.ALL_IN in legal
        ):
            return Action(type=ActionType.ALL_IN)

        return action


def ante_kind(context: DecisionContext) -> str:
    """The antes of the hand: "none", "classic" (every player) or
    "big_blind" (the big blind posts the table's ante)."""
    posters = [e for e in context.actions if e.action == "post_ante"]

    if not posters:
        return "none"

    if len(posters) == 1 and posters[0].position == Position.BB:
        return "big_blind"

    return "classic"


def _nearest(solutions: dict[int, tuple[str, ...]], depth: float) -> int:
    """The solved stack closest to ``depth``."""
    return min(solutions, key=lambda solved: abs(solved - depth))


def _margin(options: list[tuple[float, Action]]) -> float:
    """How far the best option is ahead of the next one."""
    values = sorted((value for value, _ in options), reverse=True)

    return values[0] - values[1] if len(values) > 1 else float("inf")


def effective_big_blinds(context: DecisionContext) -> float:
    """The smaller of the bot's stack and the biggest opponent's, in big
    blinds, bets of this street included."""
    me = context.player
    own = me.stack + me.current_bet
    others = [
        p.stack + p.current_bet
        for p in context.players
        if p.name != me.name and not p.folded and p.position is not None
    ]

    return min(own, max(others, default=own)) / context.big_blind


def m_ratio(context: DecisionContext) -> float:
    """The effective stack divided by the cost of one round of blinds and
    antes: how many rounds it survives without playing a hand."""
    small_blind = next(
        (e.amount for e in context.actions if e.action == "post_sb"),
        context.big_blind // 2,
    )
    antes = sum(e.amount for e in context.actions if e.action == "post_ante")
    orbit = small_blind + context.big_blind + antes

    return effective_big_blinds(context) * context.big_blind / orbit


def _shove_position(context: DecisionContext) -> Position:
    """The seat of the push/fold ranges; heads-up the button is the SB."""
    position = context.player.position
    assert position is not None
    dealt_in = sum(1 for p in context.players if p.position is not None)

    if dealt_in == 2 and position == Position.BTN:
        return Position.SB

    return FULL_RING_SHOVE_POSITIONS.get(position, position)


@cache
def _range(notation: str) -> frozenset[str]:
    return HandRange.parse(notation).labels if notation else frozenset()


def _player(context: DecisionContext, name: str) -> PlayerView:
    return next(p for p in context.players if p.name == name)


def _callers_after(context: DecisionContext, raise_event: ActionEvent) -> int:
    return sum(
        1
        for e in context.actions
        if e.street == Street.PREFLOP
        and e.sequence > raise_event.sequence
        and e.action == ActionType.CALL
    )


def _call_amount(legal: dict[ActionType, LegalAction]) -> int:
    call = legal.get(ActionType.CALL)

    return call.amount if call is not None and call.amount is not None else 0


def _shove(legal: dict[ActionType, LegalAction]) -> Action:
    for action_type in (ActionType.ALL_IN, ActionType.CALL, ActionType.CHECK):
        if action_type in legal:
            return Action(type=action_type)

    return Action(type=ActionType.FOLD)


def _check_or_fold(legal: dict[ActionType, LegalAction]) -> Action:
    if ActionType.CHECK in legal:
        return Action(type=ActionType.CHECK)

    return Action(type=ActionType.FOLD)
