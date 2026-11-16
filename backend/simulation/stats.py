"""Statistics gathered during a simulation.

Every statistic can be merged with the same statistic over other hands, so
the results of parallel workers can be combined. Only integers are summed,
which makes merging exact and independent of the number of workers; rates
and confidence intervals are derived at the end.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields

from backend.poker_engine.constants import ActionType, Street
from backend.poker_engine.hand_evaluator import HandCategory
from backend.poker_engine.models import ActionEvent, Hand

from .events import HandObserver

ACTION_CATEGORIES = ("fold", "check", "call", "bet", "raise", "all_in")
"""How actions are counted: a bet opens a street, a raise follows a bet."""

STREETS = tuple(street.value for street in Street)

CONFIDENCE_Z = 1.96
"""Normal quantile of a 95% confidence interval."""


def ratio(numerator: int, denominator: int) -> float | None:
    """Return ``numerator / denominator``, or None when nothing was counted."""
    if denominator == 0:
        return None

    return numerator / denominator


def _empty_action_counts() -> dict[str, dict[str, int]]:
    return {street: dict.fromkeys(ACTION_CATEGORIES, 0) for street in STREETS}


@dataclass
class PositionResult:
    """Results of a player from one position."""

    hands: int = 0
    net_chips: int = 0

    def merge(self, other: "PositionResult") -> None:
        self.hands += other.hands
        self.net_chips += other.net_chips


@dataclass
class PlayerStats:
    """Results and playing tendencies of one seat over many hands."""

    name: str
    bot: str
    hands: int = 0
    net_chips: int = 0
    net_chips_squared: int = 0
    """Sum of the squared net result of every hand, for the variance."""
    rebuys: int = 0
    finishes: list[int] = field(default_factory=list)
    """``finishes[k]`` counts the sessions finished in position ``k + 1``."""

    vpip_hands: int = 0
    pfr_hands: int = 0
    three_bet_opportunities: int = 0
    three_bets: int = 0
    postflop_aggressive_actions: int = 0
    postflop_calls: int = 0
    postflop_folds: int = 0
    postflop_checks: int = 0
    saw_flop: int = 0
    went_to_showdown: int = 0
    won_at_showdown: int = 0
    cbet_opportunities: int = 0
    cbets: int = 0
    fold_to_cbet_opportunities: int = 0
    folds_to_cbet: int = 0
    actions: dict[str, dict[str, int]] = field(default_factory=_empty_action_counts)
    """Number of actions per street and category."""
    positions: dict[str, PositionResult] = field(default_factory=dict)

    # --- Recording -----------------------------------------------------------

    def record_hand(self, net_chips: int, position: str | None = None) -> None:
        self.hands += 1
        self.net_chips += net_chips
        self.net_chips_squared += net_chips * net_chips

        if position is not None:
            result = self.positions.setdefault(position, PositionResult())
            result.hands += 1
            result.net_chips += net_chips

    def record_finish(self, position: int, seat_count: int) -> None:
        if not self.finishes:
            self.finishes = [0] * seat_count

        self.finishes[position - 1] += 1

    def merge(self, other: "PlayerStats") -> None:
        if other.name != self.name:
            raise ValueError(f"Cannot merge {other.name} into {self.name}.")

        for counter in fields(self):
            if counter.type is int:
                total = getattr(self, counter.name) + getattr(other, counter.name)
                setattr(self, counter.name, total)

        if other.finishes:
            if not self.finishes:
                self.finishes = [0] * len(other.finishes)

            for index, count in enumerate(other.finishes):
                self.finishes[index] += count

        for street, counts in other.actions.items():
            for category, count in counts.items():
                self.actions[street][category] += count

        for position, result in other.positions.items():
            self.positions.setdefault(position, PositionResult()).merge(result)

    # --- Win rate ------------------------------------------------------------

    def bb_per_100(self, big_blind: int) -> float | None:
        """Average win rate in big blinds per 100 hands."""
        if self.hands == 0:
            return None

        return self.net_chips / big_blind / self.hands * 100

    def standard_deviation_per_hand(self, big_blind: int) -> float | None:
        """Sample standard deviation of one hand's result, in big blinds."""
        if self.hands < 2:
            return None

        mean = self.net_chips / self.hands
        variance = (self.net_chips_squared - self.hands * mean * mean) / (
            self.hands - 1
        )

        return math.sqrt(max(0.0, variance)) / big_blind

    def standard_deviation_per_100(self, big_blind: int) -> float | None:
        """Standard deviation of the result of 100 hands, in big blinds."""
        deviation = self.standard_deviation_per_hand(big_blind)

        return None if deviation is None else deviation * 10

    def standard_error_bb_per_100(self, big_blind: int) -> float | None:
        """Standard error of the bb/100 estimate."""
        deviation = self.standard_deviation_per_hand(big_blind)

        if deviation is None:
            return None

        return deviation * 100 / math.sqrt(self.hands)

    def confidence_interval_bb_per_100(
        self, big_blind: int
    ) -> tuple[float, float] | None:
        """95% confidence interval of the bb/100 win rate."""
        win_rate = self.bb_per_100(big_blind)
        error = self.standard_error_bb_per_100(big_blind)

        if win_rate is None or error is None:
            return None

        margin = CONFIDENCE_Z * error

        return win_rate - margin, win_rate + margin

    # --- Tendencies ----------------------------------------------------------

    @property
    def vpip(self) -> float | None:
        """Share of hands where chips were put in voluntarily pre-flop."""
        return ratio(self.vpip_hands, self.hands)

    @property
    def pfr(self) -> float | None:
        """Share of hands raised pre-flop."""
        return ratio(self.pfr_hands, self.hands)

    @property
    def three_bet(self) -> float | None:
        """Share of re-raises when facing a single pre-flop raise."""
        return ratio(self.three_bets, self.three_bet_opportunities)

    @property
    def aggression_factor(self) -> float | None:
        """Post-flop (bets + raises) / calls."""
        return ratio(self.postflop_aggressive_actions, self.postflop_calls)

    @property
    def aggression_frequency(self) -> float | None:
        """Post-flop (bets + raises) / (bets + raises + calls + folds)."""
        return ratio(
            self.postflop_aggressive_actions,
            self.postflop_aggressive_actions
            + self.postflop_calls
            + self.postflop_folds,
        )

    @property
    def wtsd(self) -> float | None:
        """Share of the flops seen that went to showdown."""
        return ratio(self.went_to_showdown, self.saw_flop)

    @property
    def wsd(self) -> float | None:
        """Share of showdowns where some money was won."""
        return ratio(self.won_at_showdown, self.went_to_showdown)

    @property
    def cbet(self) -> float | None:
        """Share of flops bet by the pre-flop aggressor when checked to."""
        return ratio(self.cbets, self.cbet_opportunities)

    @property
    def fold_to_cbet(self) -> float | None:
        return ratio(self.folds_to_cbet, self.fold_to_cbet_opportunities)

    def action_frequencies(self, street: str) -> dict[str, float | None]:
        """Share of each action category on a street."""
        counts = self.actions[street]
        total = sum(counts.values())

        return {category: ratio(count, total) for category, count in counts.items()}

    # --- Elimination ---------------------------------------------------------

    @property
    def sessions(self) -> int:
        return sum(self.finishes)

    @property
    def win_rate(self) -> float | None:
        """Share of elimination sessions won."""
        if not self.finishes:
            return None

        return ratio(self.finishes[0], self.sessions)

    @property
    def average_finish(self) -> float | None:
        if not self.finishes or self.sessions == 0:
            return None

        weighted = sum(
            position * count for position, count in enumerate(self.finishes, start=1)
        )

        return weighted / self.sessions


@dataclass
class EngineLabStats:
    """Engine-level frequencies, used to validate the rules over many hands."""

    hands: int = 0
    showdowns: int = 0
    showdown_categories: list[int] = field(
        default_factory=lambda: [0] * len(HandCategory)
    )
    """Number of hands shown down, per category (one per player shown)."""
    split_pot_hands: int = 0
    side_pot_counts: dict[int, int] = field(default_factory=dict)
    """Number of showdown hands per number of side pots."""
    all_in_hands: int = 0
    runout_hands: int = 0
    """Hands where cards were dealt with no betting possible."""

    def merge(self, other: "EngineLabStats") -> None:
        self.hands += other.hands
        self.showdowns += other.showdowns
        self.split_pot_hands += other.split_pot_hands
        self.all_in_hands += other.all_in_hands
        self.runout_hands += other.runout_hands

        for index, count in enumerate(other.showdown_categories):
            self.showdown_categories[index] += count

        for side_pots, count in other.side_pot_counts.items():
            self.side_pot_counts[side_pots] = (
                self.side_pot_counts.get(side_pots, 0) + count
            )

    @property
    def showdown_frequency(self) -> float | None:
        return ratio(self.showdowns, self.hands)

    @property
    def split_pot_frequency(self) -> float | None:
        return ratio(self.split_pot_hands, self.hands)

    @property
    def all_in_frequency(self) -> float | None:
        return ratio(self.all_in_hands, self.hands)

    @property
    def runout_frequency(self) -> float | None:
        return ratio(self.runout_hands, self.hands)

    def category_frequencies(self) -> dict[str, float | None]:
        """Share of each category among the hands shown down."""
        total = sum(self.showdown_categories)

        return {
            category.name: ratio(self.showdown_categories[category], total)
            for category in HandCategory
        }


ChartPoint = tuple[int, tuple[int, ...]]
"""(hands played, cumulative net chips of every seat in seat order)."""


class StatsCollector(HandObserver):
    """Feeds every step of the hands to the player and engine statistics."""

    def __init__(
        self,
        players: Mapping[str, PlayerStats],
        engine: EngineLabStats,
        chart: list[ChartPoint],
        chart_stride: int = 1,
    ) -> None:
        self._players = players
        self._engine = engine
        self._chart = chart
        self._chart_stride = chart_stride
        self._seat_names = tuple(players)
        self._hands = 0
        self._cumulative = dict.fromkeys(players, 0)
        self._reset_hand_state(current_bet=0)

    def _reset_hand_state(self, current_bet: int) -> None:
        self._current_bet = current_bet
        self._preflop_raises = 0
        self._preflop_aggressor: str | None = None
        self._vpip: set[str] = set()
        self._pfr: set[str] = set()
        self._flop_bet_made = False
        self._cbet_live = False
        self._runout = False

    def on_hand_start(self, hand: Hand) -> None:
        self._reset_hand_state(current_bet=hand.current_bet)

    def on_action(self, hand: Hand, event: ActionEvent) -> None:
        stats = self._players[event.player]
        aggressive = event.current_bet_after > self._current_bet
        category = self._categorize(event, aggressive)
        stats.actions[event.street][category] += 1

        if event.street == Street.PREFLOP:
            self._record_preflop(event, aggressive)
        else:
            self._record_postflop(stats, event, aggressive)

        self._current_bet = event.current_bet_after

    def _categorize(self, event: ActionEvent, aggressive: bool) -> str:
        if event.action == ActionType.ALL_IN:
            return "all_in"

        if event.action == ActionType.RAISE:
            return "raise" if self._current_bet > 0 else "bet"

        return event.action

    def _record_preflop(self, event: ActionEvent, aggressive: bool) -> None:
        name = event.player

        if event.action in (ActionType.CALL, ActionType.RAISE, ActionType.ALL_IN):
            self._vpip.add(name)

        # A 3-bet opportunity is facing exactly one raise over the big blind.
        if self._preflop_raises == 1 and name != self._preflop_aggressor:
            self._players[name].three_bet_opportunities += 1

            if aggressive:
                self._players[name].three_bets += 1

        if aggressive:
            self._preflop_raises += 1
            self._preflop_aggressor = name
            self._pfr.add(name)

    def _record_postflop(
        self, stats: PlayerStats, event: ActionEvent, aggressive: bool
    ) -> None:
        if aggressive:
            stats.postflop_aggressive_actions += 1
        elif event.action == ActionType.CALL:
            stats.postflop_calls += 1
        elif event.action == ActionType.FOLD:
            stats.postflop_folds += 1
        elif event.action == ActionType.CHECK:
            stats.postflop_checks += 1

        if event.street != Street.FLOP:
            return

        is_aggressor = event.player == self._preflop_aggressor

        if not self._flop_bet_made and is_aggressor:
            stats.cbet_opportunities += 1

            if aggressive:
                stats.cbets += 1
                self._cbet_live = True
        elif self._cbet_live and not is_aggressor:
            stats.fold_to_cbet_opportunities += 1

            if event.action == ActionType.FOLD:
                stats.folds_to_cbet += 1

            if aggressive:
                self._cbet_live = False  # A raise ends the c-bet.

        if aggressive:
            self._flop_bet_made = True

    def on_street(self, hand: Hand) -> None:
        self._current_bet = 0

        if hand.street == Street.FLOP:
            for player in hand.table.get_active_players():
                self._players[player.name].saw_flop += 1

        if hand.current_player is None:
            self._runout = True

    def on_hand_end(self, hand: Hand, stacks_before: Mapping[str, int]) -> None:
        showdown = hand.showdown_evaluations
        engine = self._engine
        engine.hands += 1

        for player in hand.table.players:
            stack_before = stacks_before.get(player.name)

            if stack_before is None:
                continue

            stats = self._players[player.name]
            net_chips = player.stack - stack_before
            stats.record_hand(net_chips, player.position)
            self._cumulative[player.name] += net_chips

            if player.name in self._vpip:
                stats.vpip_hands += 1

            if player.name in self._pfr:
                stats.pfr_hands += 1

            if player.name in showdown:
                stats.went_to_showdown += 1

                if hand.payouts.get(player.name, 0) > 0:
                    stats.won_at_showdown += 1

        if showdown:
            engine.showdowns += 1

            for evaluation in showdown.values():
                engine.showdown_categories[evaluation.rank] += 1

            contested_pots = [
                result
                for result in hand.pot_results
                if len(result.eligible_players) > 1
            ]
            side_pots = max(0, len(contested_pots) - 1)
            engine.side_pot_counts[side_pots] = (
                engine.side_pot_counts.get(side_pots, 0) + 1
            )

            if any(len(result.winners) > 1 for result in hand.pot_results):
                engine.split_pot_hands += 1

        if any(player.all_in for player in hand.table.players):
            engine.all_in_hands += 1

        if self._runout:
            engine.runout_hands += 1

        self._hands += 1

        if self._hands % self._chart_stride == 0:
            self.add_chart_point()

    def add_chart_point(self) -> None:
        """Sample the cumulative net chips of every seat."""
        point = (
            self._hands,
            tuple(self._cumulative[name] for name in self._seat_names),
        )

        if not self._chart or self._chart[-1][0] != point[0]:
            self._chart.append(point)


def shift_chart(
    points: Sequence[ChartPoint], hands: int, net_chips: Sequence[int]
) -> list[ChartPoint]:
    """Offset chart points recorded after ``hands`` hands and ``net_chips``."""
    return [
        (
            point_hands + hands,
            tuple(a + b for a, b in zip(values, net_chips, strict=True)),
        )
        for point_hands, values in points
    ]


def downsample_chart(points: Sequence[ChartPoint], max_points: int) -> list[ChartPoint]:
    """Keep at most ``max_points`` evenly spread points, always keeping the last."""
    if len(points) <= max_points:
        return list(points)

    step = (len(points) - 1) / (max_points - 1)

    return [points[round(index * step)] for index in range(max_points)]
