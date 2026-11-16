"""A bot using simple heuristics: hand strength, pot odds and a bit of bluff.

Its parameters come from a ``BotProfile``; the default profile is the
original behaviour, the presets of ``profiles`` give other play styles.
"""

import random
from functools import lru_cache

from backend.application.controllers import DecisionContext, PlayerController
from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.constants import ActionType, Card, Street
from backend.poker_engine.hand_evaluator import (
    HandCategory,
    card_rank,
    card_suit,
    evaluate_rank,
    straight_high,
)

from .profiles import BASIC_PROFILE, BotProfile

# Below this strength, a hand is worth improving with its draws.
DRAW_WORTH_THRESHOLD = 0.5

# Chen score from which starting hands are rated as strong as possible.
CHEN_SCORE_FOR_FULL_STRENGTH = 12

MADE_HAND_STRENGTH: dict[HandCategory, float] = {
    HandCategory.TWO_PAIR: 0.75,
    HandCategory.THREE_OF_A_KIND: 0.82,
    HandCategory.STRAIGHT: 0.88,
    HandCategory.FLUSH: 0.9,
    HandCategory.FULL_HOUSE: 0.95,
    HandCategory.FOUR_OF_A_KIND: 1.0,
    HandCategory.STRAIGHT_FLUSH: 1.0,
}


# The strength functions are pure functions of the cards: caching them only
# saves work. A hand is read several times per street (once per decision),
# and every player reads the same board.
STRENGTH_CACHE_SIZE = 4096


@lru_cache(maxsize=STRENGTH_CACHE_SIZE)
def preflop_strength(hole_cards: tuple[Card, ...]) -> float:
    """Rate two hole cards between 0 and 1 with the Chen formula."""
    return min(1.0, max(0.0, _chen_score(hole_cards) / CHEN_SCORE_FOR_FULL_STRENGTH))


def _chen_score(hole_cards: tuple[Card, ...]) -> float:
    high, low = sorted((card_rank(card) for card in hole_cards), reverse=True)

    high_card_points = {14: 10.0, 13: 8.0, 12: 7.0, 11: 6.0}
    score = high_card_points.get(high, high / 2)

    if high == low:
        return max(score * 2, 5.0)

    if card_suit(hole_cards[0]) == card_suit(hole_cards[1]):
        score += 2

    gap = high - low - 1
    score -= {0: 0, 1: 1, 2: 2, 3: 4}.get(gap, 5)

    if gap <= 1 and high < 12:
        score += 1

    return score


@lru_cache(maxsize=STRENGTH_CACHE_SIZE)
def postflop_strength(
    hole_cards: tuple[Card, ...],
    community_cards: tuple[Card, ...],
) -> float:
    """Rate a hand between 0 and 1 from the made hand and its draws."""
    category, tiebreaker = evaluate_rank([*hole_cards, *community_cards])
    board_category = _board_category(community_cards)

    # A hand that only plays the board has no value of its own.
    if category == board_category and category != HandCategory.PAIR:
        strength = 0.15
    elif category in MADE_HAND_STRENGTH:
        strength = MADE_HAND_STRENGTH[category]
    elif category == HandCategory.PAIR:
        strength = _pair_strength(
            pair_rank=tiebreaker[0],
            hole_ranks=[card_rank(card) for card in hole_cards],
            board_ranks=[card_rank(card) for card in community_cards],
        )
    else:
        strength = 0.15

    if len(community_cards) < 5 and strength < DRAW_WORTH_THRESHOLD:
        strength += _draw_bonus(hole_cards + community_cards)

    return strength


@lru_cache(maxsize=STRENGTH_CACHE_SIZE)
def _board_category(community_cards: tuple[Card, ...]) -> HandCategory | None:
    if len(community_cards) < 5:
        ranks = [card_rank(card) for card in community_cards]
        most_common = max(ranks.count(rank) for rank in ranks)
        return HandCategory.PAIR if most_common == 2 else None

    return evaluate_rank(list(community_cards))[0]


def _pair_strength(
    pair_rank: int,
    hole_ranks: list[int],
    board_ranks: list[int],
) -> float:
    if pair_rank not in hole_ranks:
        return 0.2  # The pair is on the board: everyone has it.

    if pair_rank >= max(board_ranks):
        return 0.65  # Top pair or overpair.

    return 0.4


def _draw_bonus(cards: tuple[Card, ...]) -> float:
    suits = [card_suit(card) for card in cards]

    if max(suits.count(suit) for suit in set(suits)) == 4:
        return 0.2

    ranks = {card_rank(card) for card in cards}
    has_open_ended_draw = any(
        straight_high([*ranks, missing]) is not None
        and straight_high([*ranks, missing + 5]) is not None
        for missing in range(2, 10)
        if not {missing, missing + 5} & ranks
    )

    return 0.15 if has_open_ended_draw else 0.0


class BasicBot(PlayerController):
    """Plays its hand strength against the pot odds, with occasional bluffs."""

    def __init__(
        self,
        rng: random.Random | None = None,
        profile: BotProfile = BASIC_PROFILE,
    ) -> None:
        self._rng = rng or random.Random()
        self.profile = profile

    def choose_action(self, context: DecisionContext) -> Action:
        profile = self.profile
        legal = {action.type: action for action in context.legal_actions}
        strength = self._estimate_strength(context)
        call_action = legal.get(ActionType.CALL)

        if call_action is None:
            return self._act_when_checked_to(context, legal, strength)

        assert call_action.amount is not None
        pot_odds = call_action.amount / (context.pot + call_action.amount)

        is_cheap_to_call = (
            call_action.amount <= profile.cheap_call_big_blinds * context.big_blind
        )

        if strength >= profile.raise_threshold or (
            strength >= profile.cheap_raise_threshold and is_cheap_to_call
        ):
            return self._raise_or(
                context,
                legal,
                fraction=profile.raise_pot_fraction,
                fallback=ActionType.CALL,
            )

        if (
            strength >= profile.call_threshold
            or (
                strength >= profile.good_threshold
                and pot_odds <= profile.good_max_pot_odds
            )
            or (
                strength >= profile.marginal_threshold
                and pot_odds <= profile.marginal_max_pot_odds
            )
        ):
            return self._call_or_raise(context, legal)

        if self._chance(profile.bluff_raise_probability):
            return self._raise_or(
                context,
                legal,
                fraction=profile.raise_pot_fraction,
                fallback=ActionType.FOLD,
            )

        return Action(type=ActionType.FOLD)

    def _chance(self, probability: float) -> bool:
        """Draw a random event; a zero probability draws no random number."""
        return probability > 0 and self._rng.random() < probability

    def _call_or_raise(
        self, context: DecisionContext, legal: dict[ActionType, LegalAction]
    ) -> Action:
        if self._chance(self.profile.raise_instead_of_call_probability):
            return self._raise_or(
                context,
                legal,
                fraction=self.profile.raise_pot_fraction,
                fallback=ActionType.CALL,
            )

        return Action(type=ActionType.CALL)

    def _estimate_strength(self, context: DecisionContext) -> float:
        if not context.community_cards:
            strength = (
                preflop_strength(context.hole_cards)
                + self.profile.preflop_strength_bonus
            )
        else:
            strength = postflop_strength(context.hole_cards, context.community_cards)

        opponents = sum(
            1
            for player in context.players
            if not player.folded and player.name != context.player.name
        )

        # A hand loses value against several opponents.
        return strength - self.profile.multiway_penalty * max(0, opponents - 1)

    def _act_when_checked_to(
        self,
        context: DecisionContext,
        legal: dict[ActionType, LegalAction],
        strength: float,
    ) -> Action:
        profile = self.profile

        if strength >= profile.strong_bet_threshold:
            bet_probability = profile.value_bet_probability
        elif strength >= profile.medium_bet_threshold:
            bet_probability = profile.medium_bet_probability
        else:
            bet_probability = profile.bluff_probability  # Occasional bluff.

        wants_to_bet = self._rng.random() < bet_probability

        if not wants_to_bet and self._is_cbet_spot(context):
            wants_to_bet = self._chance(profile.cbet_probability)

        if wants_to_bet:
            return self._raise_or(
                context,
                legal,
                fraction=profile.bet_pot_fraction,
                fallback=ActionType.CHECK,
            )

        return Action(type=ActionType.CHECK)

    def _is_cbet_spot(self, context: DecisionContext) -> bool:
        """True on the flop when this bot made the last pre-flop raise."""
        if context.street != Street.FLOP:
            return False

        aggressor = None

        for event in context.actions:
            if event.street == Street.PREFLOP and event.action in (
                ActionType.RAISE,
                ActionType.ALL_IN,
            ):
                aggressor = event.player

        return aggressor == context.player.name

    def _raise_or(
        self,
        context: DecisionContext,
        legal: dict[ActionType, LegalAction],
        fraction: float,
        fallback: ActionType,
    ) -> Action:
        """Bet or raise by a fraction of the pot, or fall back if impossible."""
        raise_action = legal.get(ActionType.RAISE)

        if raise_action is None:
            # Only an all-in can raise here: commit with it only when it is
            # the fallback's natural extension (a strong hand facing a bet).
            if ActionType.ALL_IN in legal and fallback == ActionType.CALL:
                return Action(type=ActionType.ALL_IN)

            return Action(type=fallback)

        assert raise_action.min_amount is not None
        assert raise_action.max_amount is not None

        pot_after_call = context.pot + context.current_bet - context.player.current_bet
        target = context.current_bet + int(fraction * pot_after_call)
        target = max(target, context.current_bet + context.big_blind)
        amount = min(max(target, raise_action.min_amount), raise_action.max_amount)

        return Action(type=ActionType.RAISE, amount=amount)
