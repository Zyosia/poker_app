"""Mergeable statistics of tournament and Spin & Go runs.

Every field is an integer sum, so the totals of several workers merge
exactly, and in batch order the merged result is the same for any number of
workers. Rates and confidence intervals are computed from the sums.
"""

import math
from dataclasses import dataclass, field, fields
from fractions import Fraction

from backend.application.tournament import Finish

from .stats import CONFIDENCE_Z, ratio


@dataclass
class TournamentPlayerStats:
    """Results of one bot over many tournaments."""

    name: str
    bot: str
    seats: int
    tournaments: int = 0
    wins: int = 0
    in_the_money: int = 0
    places: list[int] = field(default_factory=list)
    """Number of finishes at each place, 1st first."""
    place_sum: int = 0
    invested: int = 0
    prizes: int = 0
    profit_squares: int = 0
    invested_squares: int = 0
    profit_invested: int = 0
    rebuys: int = 0
    add_ons: int = 0

    def __post_init__(self) -> None:
        if not self.places:
            self.places = [0] * self.seats

    def record(self, finish: Finish) -> None:
        profit = finish.profit
        self.tournaments += 1
        self.wins += finish.place == 1
        self.in_the_money += finish.prize > 0
        self.places[finish.place - 1] += 1
        self.place_sum += finish.place
        self.invested += finish.invested
        self.prizes += finish.prize
        self.profit_squares += profit * profit
        self.invested_squares += finish.invested * finish.invested
        self.profit_invested += profit * finish.invested
        self.rebuys += finish.rebuys
        self.add_ons += finish.add_ons

    def merge(self, other: "TournamentPlayerStats") -> None:
        for item in fields(self):
            if item.name in ("name", "bot", "seats"):
                continue

            if item.name == "places":
                for index, count in enumerate(other.places):
                    self.places[index] += count
                continue

            setattr(
                self, item.name, getattr(self, item.name) + getattr(other, item.name)
            )

    # --- Rates --------------------------------------------------------------

    @property
    def win_rate(self) -> float | None:
        return ratio(self.wins, self.tournaments)

    @property
    def itm_rate(self) -> float | None:
        return ratio(self.in_the_money, self.tournaments)

    @property
    def average_place(self) -> float | None:
        return ratio(self.place_sum, self.tournaments)

    @property
    def profit(self) -> int:
        return self.prizes - self.invested

    @property
    def roi(self) -> float | None:
        """Return on investment: (prizes - invested) / invested."""
        return ratio(self.profit, self.invested)

    @property
    def roi_standard_error(self) -> float | None:
        """Standard error of the ROI (a ratio estimator, by the delta method)."""
        count = self.tournaments
        roi = self.roi

        if roi is None or count < 2:
            return None

        residuals = (
            self.profit_squares
            - 2 * roi * self.profit_invested
            + roi * roi * self.invested_squares
        )

        return math.sqrt(max(0.0, residuals) * count / (count - 1)) / self.invested

    @property
    def roi_ci95(self) -> tuple[float, float] | None:
        roi, error = self.roi, self.roi_standard_error

        if roi is None or error is None:
            return None

        return roi - CONFIDENCE_Z * error, roi + CONFIDENCE_Z * error

    def roi_without_multiplier(self, expected_multiplier: Fraction) -> float | None:
        """Spin & Go ROI if every game paid its expected prize pool.

        The multiplier draw is the main source of variance: replacing it by
        its expected value (the winner takes ``expected_multiplier`` buy-ins)
        compares bots on their play only.
        """
        win_rate = self.win_rate

        if win_rate is None:
            return None

        return float(expected_multiplier) * win_rate - 1

    def roi_without_multiplier_error(
        self, expected_multiplier: Fraction
    ) -> float | None:
        win_rate = self.win_rate

        if win_rate is None or self.tournaments < 2:
            return None

        deviation = math.sqrt(win_rate * (1 - win_rate) / self.tournaments)

        return float(expected_multiplier) * deviation

    def place_distribution(self) -> list[float]:
        """Share of the tournaments finished at each place."""
        return [ratio(count, self.tournaments) or 0.0 for count in self.places]


@dataclass
class TournamentTotals:
    """Mergeable totals over a set of tournaments."""

    players: dict[str, TournamentPlayerStats]
    tournaments: int = 0
    capped: int = 0
    """Tournaments stopped by the hand cap, survivors ranked by stack."""
    hands: int = 0
    levels_reached: int = 0
    """Sum over the tournaments of the last level number played (1 = first)."""
    multiplier_counts: dict[int, int] = field(default_factory=dict)

    def merge(self, other: "TournamentTotals") -> None:
        if list(self.players) != list(other.players):
            raise ValueError("Cannot merge totals of different tables.")

        for name, stats in other.players.items():
            self.players[name].merge(stats)

        self.tournaments += other.tournaments
        self.capped += other.capped
        self.hands += other.hands
        self.levels_reached += other.levels_reached

        for multiplier, count in other.multiplier_counts.items():
            self.multiplier_counts[multiplier] = (
                self.multiplier_counts.get(multiplier, 0) + count
            )

    @property
    def average_hands(self) -> float | None:
        return ratio(self.hands, self.tournaments)

    @property
    def average_level(self) -> float | None:
        return ratio(self.levels_reached, self.tournaments)
