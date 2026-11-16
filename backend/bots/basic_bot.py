"""A bot using simple heuristics: hand strength, pot odds and a bit of bluff."""

import random
from collections import Counter

from backend.application.controllers import DecisionContext, PlayerController
from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.constants import ActionType, Card
from backend.poker_engine.hand_evaluator import (
    HandCategory,
    card_rank,
    card_suit,
    evaluate_hand,
    get_straight_high,
)

PREMIUM_HAND = 0.9
STRONG_HAND = 0.75
GOOD_HAND = 0.5
MARGINAL_HAND = 0.3

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


def postflop_strength(
    hole_cards: tuple[Card, ...],
    community_cards: tuple[Card, ...],
) -> float:
    """Rate a hand between 0 and 1 from the made hand and its draws."""
    evaluation = evaluate_hand(list(hole_cards), list(community_cards))
    board_ranks = [card_rank(card) for card in community_cards]
    board_category = _board_category(community_cards)

    # A hand that only plays the board has no value of its own.
    if evaluation.rank == board_category and evaluation.rank != HandCategory.PAIR:
        strength = 0.15
    elif evaluation.rank in MADE_HAND_STRENGTH:
        strength = MADE_HAND_STRENGTH[evaluation.rank]
    elif evaluation.rank == HandCategory.PAIR:
        strength = _pair_strength(
            pair_rank=evaluation.tiebreaker[0],
            hole_ranks=[card_rank(card) for card in hole_cards],
            board_ranks=board_ranks,
        )
    else:
        strength = 0.15

    if len(community_cards) < 5 and strength < GOOD_HAND:
        strength += _draw_bonus(hole_cards + community_cards)

    return strength


def _board_category(community_cards: tuple[Card, ...]) -> HandCategory | None:
    if len(community_cards) < 5:
        counts = Counter(card_rank(card) for card in community_cards)
        return HandCategory.PAIR if max(counts.values()) == 2 else None

    return evaluate_hand([], list(community_cards)).rank


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
    suit_counts = Counter(card_suit(card) for card in cards)

    if max(suit_counts.values()) == 4:
        return 0.2

    ranks = {card_rank(card) for card in cards}
    has_open_ended_draw = any(
        get_straight_high([*ranks, missing]) is not None
        and get_straight_high([*ranks, missing + 5]) is not None
        for missing in range(2, 10)
        if not {missing, missing + 5} & ranks
    )

    return 0.15 if has_open_ended_draw else 0.0


class BasicBot(PlayerController):
    """Plays its hand strength against the pot odds, with occasional bluffs."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    def choose_action(self, context: DecisionContext) -> Action:
        legal = {action.type: action for action in context.legal_actions}
        strength = self._estimate_strength(context)
        call_action = legal.get(ActionType.CALL)

        if call_action is None:
            return self._act_when_checked_to(context, legal, strength)

        assert call_action.amount is not None
        pot_odds = call_action.amount / (context.pot + call_action.amount)

        is_cheap_to_call = call_action.amount <= 3 * context.big_blind

        if strength >= PREMIUM_HAND or (strength >= STRONG_HAND and is_cheap_to_call):
            return self._raise_or(
                context, legal, fraction=0.75, fallback=ActionType.CALL
            )

        if strength >= STRONG_HAND:
            return Action(type=ActionType.CALL)

        if strength >= GOOD_HAND and pot_odds <= 0.4:
            return Action(type=ActionType.CALL)

        if strength >= MARGINAL_HAND and pot_odds <= 0.25:
            return Action(type=ActionType.CALL)

        return Action(type=ActionType.FOLD)

    def _estimate_strength(self, context: DecisionContext) -> float:
        if not context.community_cards:
            strength = preflop_strength(context.hole_cards)
        else:
            strength = postflop_strength(context.hole_cards, context.community_cards)

        opponents = sum(
            1
            for player in context.players
            if not player.folded and player.name != context.player.name
        )

        # A hand loses value against several opponents.
        return strength - 0.02 * max(0, opponents - 1)

    def _act_when_checked_to(
        self,
        context: DecisionContext,
        legal: dict[ActionType, LegalAction],
        strength: float,
    ) -> Action:
        if strength >= STRONG_HAND:
            bet_probability = 0.85
        elif strength >= GOOD_HAND:
            bet_probability = 0.5
        else:
            bet_probability = 0.08  # Occasional bluff.

        if self._rng.random() < bet_probability:
            return self._raise_or(
                context, legal, fraction=0.6, fallback=ActionType.CHECK
            )

        return Action(type=ActionType.CHECK)

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
