"""The human player's stats across saved sessions ("My stats", V1.1).

Every saved hand is fed to the Bot Arena's ``StatsCollector`` (Beta 1.0), so
VPIP, PFR, aggression and the rest mean exactly what they mean in the Bot
Arena. The hands are rebuilt from their records: what the collector reads
(the actions, the streets, folds, positions, stacks, showdown and payouts)
is in the hand history of every session format version.

Results are kept apart by mode: chips won in cash games (in big blinds, as
the stakes may differ from one session to the next), and finishes, prizes
and ROI in tournaments and Spin & Go.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from backend.application.game_modes import GameMode
from backend.application.hand_records import FORCED_ACTIONS, HandRecord, SessionRecord
from backend.poker_engine.constants import ActionType
from backend.poker_engine.models import Hand, Player, StreetEvent, Table

from .events import HandObserver
from .stats import CONFIDENCE_Z, EngineLabStats, PlayerStats, StatsCollector, ratio

YOU = "You"


def feed_record(record: HandRecord, observer: HandObserver) -> None:
    """Notify ``observer`` of every step of a recorded hand, as if played.

    Only what the observers read is rebuilt: ``hand.current_player`` is None
    exactly on the streets dealt without any betting (an all-in called).
    Stacks before the hand are unknown before format 4: each player is then
    given the chips they put in, which keeps every net result exact.
    """
    stacks_before = {
        name: seat.stack if (seat := record.seat(name)) else record.contributed(name)
        for name in record.players
    }
    players = [
        Player(name=name, stack=stack, position=record.position_of(name))
        for name, stack in stacks_before.items()
    ]
    by_name = {player.name: player for player in players}
    hand = Hand(
        table=Table(players=players),
        min_bet=record.big_blind,
        blind_level=record.blind_level,
    )
    hand.current_bet = record.big_blind
    streets = iter(record.streets[1:])  # The pre-flop comes with the deal.
    observer.on_hand_start(hand)

    for event in record.actions:
        if event.action in FORCED_ACTIONS:
            continue

        while hand.street != event.street:
            _deal(hand, next(streets), players[0], observer)

        if event.action == ActionType.FOLD:
            by_name[event.player].folded = True

        observer.on_action(hand, event)

    for street in streets:  # Dealt with nobody able to bet.
        _deal(hand, street, None, observer)

    for player in players:
        put_in = record.contributed(player.name)
        player.stack = (
            stacks_before[player.name] - put_in + record.payouts.get(player.name, 0)
        )
        player.all_in = (
            put_in == stacks_before[player.name]
            if record.seats is not None
            else any(
                e.player == player.name and e.action == ActionType.ALL_IN
                for e in record.actions
            )
        )

    hand.showdown_evaluations = dict(record.showdown)
    hand.payouts = dict(record.payouts)
    hand.pot_results = list(record.pot_results)
    hand.finished = True
    observer.on_hand_end(hand, stacks_before)


def _deal(
    hand: Hand, street: StreetEvent, to_act: Player | None, observer: HandObserver
) -> None:
    hand.street = street.street
    hand.community_cards = list(street.community_cards)
    hand.current_player = to_act
    observer.on_street(hand)


@dataclass
class CashResults:
    """Chips won in cash games, in chips and in big blinds."""

    hands: int = 0
    net_chips: int = 0
    net_big_blinds: float = 0.0
    big_blinds_squared: float = 0.0

    def record(self, net_chips: int, big_blind: int) -> None:
        big_blinds = net_chips / big_blind
        self.hands += 1
        self.net_chips += net_chips
        self.net_big_blinds += big_blinds
        self.big_blinds_squared += big_blinds * big_blinds

    @property
    def bb_per_100(self) -> float | None:
        if self.hands == 0:
            return None

        return self.net_big_blinds / self.hands * 100

    @property
    def confidence_interval(self) -> tuple[float, float] | None:
        """95% confidence interval of the bb/100 win rate."""
        rate = self.bb_per_100

        if rate is None or self.hands < 2:
            return None

        mean = self.net_big_blinds / self.hands
        variance = (self.big_blinds_squared - self.hands * mean * mean) / (
            self.hands - 1
        )
        margin = CONFIDENCE_Z * math.sqrt(max(0.0, variance) / self.hands) * 100

        return rate - margin, rate + margin


@dataclass
class TournamentResults:
    """Finished tournaments (or Spin & Go) and their prizes."""

    played: int = 0
    wins: int = 0
    in_the_money: int = 0
    invested: int = 0
    prizes: int = 0
    unfinished: int = 0
    """Left before the end, or saved before the results were recorded."""

    @property
    def profit(self) -> int:
        return self.prizes - self.invested

    @property
    def roi(self) -> float | None:
        if self.invested == 0:
            return None

        return self.profit / self.invested

    @property
    def itm(self) -> float | None:
        return ratio(self.in_the_money, self.played)


@dataclass
class MyStats:
    sessions: int = 0
    hands: int = 0
    replayable_hands: int = 0
    tendencies: PlayerStats = field(
        default_factory=lambda: PlayerStats(name=YOU, bot="human")
    )
    cash: CashResults = field(default_factory=CashResults)
    positions: dict[str, CashResults] = field(default_factory=dict)
    """Cash-game results by position."""
    tournaments: TournamentResults = field(default_factory=TournamentResults)
    spins: TournamentResults = field(default_factory=TournamentResults)


def compute_my_stats(
    sessions: Iterable[SessionRecord], mode: GameMode | None = None
) -> MyStats:
    """The human's stats over ``sessions`` (only those of ``mode`` if set)."""
    stats = MyStats()

    for session in sessions:
        if mode is not None and session.mode != mode:
            continue

        hands = [
            hand
            for hand in session.hands
            if hand.finished and session.human in hand.players
        ]
        stats.sessions += 1
        stats.hands += len(hands)
        stats.replayable_hands += sum(hand.replayable for hand in hands)
        stats.tendencies.merge(_tendencies(session, hands))

        if session.mode == GameMode.CASH:
            _add_cash_results(stats, session.human, hands)
        else:
            results = (
                stats.spins if session.mode == GameMode.SPIN else stats.tournaments
            )
            _add_finish(results, session)

    return stats


def _tendencies(session: SessionRecord, hands: list[HandRecord]) -> PlayerStats:
    names = {name for hand in hands for name in hand.players} | {session.human}
    players = {
        name: PlayerStats(name=YOU if name == session.human else name, bot="")
        for name in names
    }
    # No chart: the stride is never reached.
    collector = StatsCollector(
        players, EngineLabStats(), chart=[], chart_stride=len(hands) + 1
    )

    for hand in hands:
        feed_record(hand, collector)

    return players[session.human]


def _add_cash_results(stats: MyStats, human: str, hands: list[HandRecord]) -> None:
    for hand in hands:
        net = hand.net_result(human)
        stats.cash.record(net, hand.big_blind)
        position = hand.position_of(human)

        if position is not None:
            stats.positions.setdefault(position, CashResults()).record(
                net, hand.big_blind
            )


def _add_finish(results: TournamentResults, session: SessionRecord) -> None:
    finish = session.finish

    if finish is None:
        results.unfinished += 1
        return

    results.played += 1
    results.wins += finish.place == 1
    results.in_the_money += finish.prize > 0
    results.invested += finish.invested
    results.prizes += finish.prize
