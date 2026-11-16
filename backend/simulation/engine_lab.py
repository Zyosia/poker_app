"""Validation of the hand evaluator against the theoretical 7-card frequencies."""

import math
import random
import time
from dataclasses import dataclass

from backend.poker_engine.deck import Deck
from backend.poker_engine.hand_evaluator import HandCategory, evaluate_hand

SEVEN_CARD_COMBINATIONS = math.comb(52, 7)

SEVEN_CARD_CATEGORY_COUNTS: dict[HandCategory, int] = {
    HandCategory.HIGH_CARD: 23_294_460,
    HandCategory.PAIR: 58_627_800,
    HandCategory.TWO_PAIR: 31_433_400,
    HandCategory.THREE_OF_A_KIND: 6_461_620,
    HandCategory.STRAIGHT: 6_180_020,
    HandCategory.FLUSH: 4_047_644,
    HandCategory.FULL_HOUSE: 3_473_184,
    HandCategory.FOUR_OF_A_KIND: 224_848,
    HandCategory.STRAIGHT_FLUSH: 41_584,
}
"""Number of 7-card hands whose best five cards fall in each category."""


@dataclass(frozen=True)
class CategoryCheck:
    """Observed frequency of a category against its theoretical probability."""

    category: HandCategory
    observed: int
    samples: int

    @property
    def expected_probability(self) -> float:
        return SEVEN_CARD_CATEGORY_COUNTS[self.category] / SEVEN_CARD_COMBINATIONS

    @property
    def observed_probability(self) -> float:
        return self.observed / self.samples

    @property
    def z_score(self) -> float:
        """Distance to the expectation, in binomial standard deviations."""
        probability = self.expected_probability
        deviation = math.sqrt(self.samples * probability * (1 - probability))

        return (self.observed - self.samples * probability) / deviation


@dataclass(frozen=True)
class SevenCardReport:
    checks: tuple[CategoryCheck, ...]
    duration_seconds: float

    @property
    def samples(self) -> int:
        return self.checks[0].samples

    @property
    def max_abs_z_score(self) -> float:
        return max(abs(check.z_score) for check in self.checks)

    @property
    def evaluations_per_second(self) -> float:
        return self.samples / self.duration_seconds if self.duration_seconds else 0.0


def check_seven_card_frequencies(samples: int, seed: int) -> SevenCardReport:
    """Evaluate ``samples`` random 7-card hands and compare with the theory."""
    if samples <= 0:
        raise ValueError("At least one sample is required.")

    rng = random.Random(seed)
    counts = dict.fromkeys(HandCategory, 0)
    started = time.perf_counter()

    for _ in range(samples):
        cards = Deck(rng).cards[:7]
        counts[evaluate_hand(cards[:2], cards[2:]).rank] += 1

    return SevenCardReport(
        checks=tuple(
            CategoryCheck(category=category, observed=counts[category], samples=samples)
            for category in HandCategory
        ),
        duration_seconds=time.perf_counter() - started,
    )
