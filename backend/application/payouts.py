"""Prize pools, payout structures and the Spin & Go prize multipliers.

Amounts are whole units of a fictional currency. Rounding never loses a
unit: the remainders of a split go to the higher places.
"""

import random
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class PayoutStructure:
    """Share of the prize pool for each paid place, in whole percents."""

    name: str
    percentages: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.percentages or any(share <= 0 for share in self.percentages):
            raise ValueError("Every paid place needs a positive share.")

        if sum(self.percentages) != 100:
            raise ValueError("The shares of a payout structure must sum to 100.")

        if list(self.percentages) != sorted(self.percentages, reverse=True):
            raise ValueError("A place cannot pay more than a better place.")

    @property
    def places_paid(self) -> int:
        return len(self.percentages)

    def prizes(self, prize_pool: int, entrants: int) -> list[int]:
        """The prize of every place from 1st to ``entrants``-th.

        Places beyond the paid places, or beyond the entrants, win nothing;
        with fewer entrants than paid places, the shares of the missing
        places go to the places that exist, best place first. Units lost to
        rounding go to the higher places, one each.
        """
        if prize_pool < 0:
            raise ValueError("The prize pool cannot be negative.")

        if entrants < 1:
            raise ValueError("A tournament has at least one entrant.")

        shares = list(self.percentages[:entrants])
        shares[0] += sum(self.percentages[entrants:])
        prizes = [prize_pool * share // 100 for share in shares]

        for place in range(prize_pool - sum(prizes)):
            prizes[place % len(prizes)] += 1

        return prizes + [0] * (entrants - len(prizes))


WINNER_TAKES_ALL = PayoutStructure("Winner takes all", (100,))
TOP_TWO = PayoutStructure("65 / 35", (65, 35))
TOP_THREE = PayoutStructure("50 / 30 / 20", (50, 30, 20))
HIGH_MULTIPLIER = PayoutStructure("80 / 10 / 10", (80, 10, 10))

PAYOUT_PRESETS: tuple[PayoutStructure, ...] = (WINNER_TAKES_ALL, TOP_TWO, TOP_THREE)


def default_payout(entrants: int) -> PayoutStructure:
    """Winner takes all up to 3 players, 65 / 35 from 4 players."""
    return WINNER_TAKES_ALL if entrants <= 3 else TOP_TWO


def split_prizes(prizes: list[int], shares: int) -> list[int]:
    """Split the combined ``prizes`` of tied places between ``shares`` players.

    Indivisible units go one each to the first players, in the order given
    (the caller orders the tied players deterministically).
    """
    base, remainder = divmod(sum(prizes), shares)

    return [base + (1 if index < remainder else 0) for index in range(shares)]


# --- Spin & Go multipliers --------------------------------------------------


@dataclass(frozen=True)
class Multiplier:
    """One prize multiplier and its chance of being drawn.

    ``weight`` is relative to the other entries of the table, so the
    probabilities are exact fractions. The prize pool is ``value`` buy-ins.
    """

    value: int
    weight: int
    payout: PayoutStructure = WINNER_TAKES_ALL


@dataclass(frozen=True)
class MultiplierTable:
    """The distribution the prize multiplier of a Spin & Go is drawn from."""

    name: str
    entries: tuple[Multiplier, ...]

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError("A multiplier table needs at least one entry.")

        if any(entry.value <= 0 or entry.weight <= 0 for entry in self.entries):
            raise ValueError("Multipliers and their weights must be positive.")

    @property
    def total_weight(self) -> int:
        return sum(entry.weight for entry in self.entries)

    def probability(self, entry: Multiplier) -> Fraction:
        return Fraction(entry.weight, self.total_weight)

    @property
    def expected_value(self) -> Fraction:
        """Expected prize pool, in buy-ins."""
        return sum(
            (entry.value * self.probability(entry) for entry in self.entries),
            Fraction(0),
        )

    def draw(self, rng: random.Random) -> Multiplier:
        """Draw a multiplier; one random integer per draw."""
        ticket = rng.randrange(self.total_weight)

        for entry in self.entries:
            if ticket < entry.weight:
                return entry

            ticket -= entry.weight

        raise AssertionError("The ticket is always below the total weight.")


# Weights are out of 10,000. Fair: the expected prize pool is exactly the
# three buy-ins paid (no rake).
FAIR_MULTIPLIERS = MultiplierTable(
    "Fair (no rake)",
    (
        Multiplier(2, 5300),
        Multiplier(3, 3900),
        Multiplier(5, 600),
        Multiplier(10, 180),
        Multiplier(100, 19, HIGH_MULTIPLIER),
        Multiplier(1000, 1, HIGH_MULTIPLIER),
    ),
)

# Close to real sites: 2.78 buy-ins expected for 3 paid, about 7% of rake.
REALISTIC_MULTIPLIERS = MultiplierTable(
    "Realistic (~7% rake)",
    (
        Multiplier(2, 7500),
        Multiplier(3, 1700),
        Multiplier(5, 600),
        Multiplier(10, 180),
        Multiplier(100, 19, HIGH_MULTIPLIER),
        Multiplier(1000, 1, HIGH_MULTIPLIER),
    ),
)

MULTIPLIER_TABLES: tuple[MultiplierTable, ...] = (
    FAIR_MULTIPLIERS,
    REALISTIC_MULTIPLIERS,
)
