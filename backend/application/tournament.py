"""Single-table tournaments and Spin & Go.

A ``Tournament`` plays hands one step at a time, like ``PokerGame``, until
one player holds every chip. Rules and choices:

- **Blind levels** advance by number of hands (always in simulations and
  tests) or by time when the application drives a human game; time is
  measured by a ``LevelClock`` given by the caller, never by the engine.
  Levels only change between two hands.
- **Moving button**: before each hand the button moves to the next player
  who still has chips. There is no dead-button rule; when the table goes
  heads-up, the engine's heads-up rules apply (the button posts the small
  blind, acts first pre-flop and last after the flop).
- **Eliminations**: players busted in the same hand are ranked by their stack
  at the start of that hand, the bigger stack finishing higher. Players with
  exactly equal stacks share their places: each gets the best place of the
  group, and the prizes of the places they cover are split between them,
  indivisible units going one each to the first of them clockwise from the
  left of the button.
- **Payouts**: whole units, see ``payouts.PayoutStructure``. The prize pool
  is the buy-ins plus every rebuy and add-on, or a multiple of the buy-in for
  a Spin & Go.
- **Rebuys and add-on** (off by default): during the first ``levels`` levels,
  a player at or below ``threshold`` chips (between hands) may rebuy. Once,
  when the rebuy period ends, every player may take an add-on. Both add to
  the prize pool. Bots always rebuy when allowed, and take the add-on when
  at or below the starting stack; a human decides through the interface.
"""

import random
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from backend.poker_engine.betting import apply_action
from backend.poker_engine.blinds import BlindLevel, BlindStructure
from backend.poker_engine.constants import MAX_TABLE_SEATS
from backend.poker_engine.deck import Deck
from backend.poker_engine.hand import advance_hand, start_hand
from backend.poker_engine.models import ActionEvent, Hand, Player
from backend.poker_engine.session import GameConfig, GameSession

from .controllers import (
    DecisionContext,
    GameFormat,
    HumanController,
    PlayerController,
    build_decision_context,
    notify_hand_end,
)
from .payouts import (
    Multiplier,
    MultiplierTable,
    PayoutStructure,
    default_payout,
    split_prizes,
)
from .structures import SPIN_HYPER_TURBO, SPIN_PLAYERS, SPIN_STARTING_STACK

MIN_PLAYERS = 2
MAX_PLAYERS = MAX_TABLE_SEATS

HandEndCallback = Callable[[Hand, Mapping[str, int]], None]


@dataclass(frozen=True)
class RebuyRules:
    """Optional rebuys during the first levels, then one add-on."""

    levels: int
    """Rebuys are allowed while the level index is below this number."""
    threshold: int
    """A player may rebuy at or below this many chips."""
    rebuy_stack: int
    add_on_stack: int | None = None
    """Chips of the add-on, or None for no add-on."""
    max_rebuys: int | None = None
    """Rebuys allowed per player; None for no limit."""

    def __post_init__(self) -> None:
        if self.levels <= 0 or self.threshold < 0 or self.rebuy_stack <= 0:
            raise ValueError("Invalid rebuy rules.")

        if self.add_on_stack is not None and self.add_on_stack <= 0:
            raise ValueError("The add-on stack must be positive.")


@dataclass(frozen=True)
class TournamentConfig:
    """How a tournament is played. Rebuys and add-ons cost one buy-in."""

    structure: BlindStructure
    starting_stack: int
    buy_in: int = 100
    payout: PayoutStructure | None = None
    """None: the default payout for the number of players."""
    rebuys: RebuyRules | None = None
    max_hands: int | None = None
    """Safety cap: past it, the survivors are ranked by stack."""

    def __post_init__(self) -> None:
        if self.starting_stack <= 0:
            raise ValueError("The starting stack must be positive.")

        if self.buy_in < 0:
            raise ValueError("The buy-in cannot be negative.")

        if self.max_hands is not None and self.max_hands <= 0:
            raise ValueError("The hand cap must be positive.")

    def payout_for(self, entrants: int) -> PayoutStructure:
        return self.payout or default_payout(entrants)


@dataclass(frozen=True)
class Finish:
    """The final result of one player."""

    name: str
    place: int
    prize: int
    invested: int
    """Buy-in plus rebuys and add-on."""
    eliminated_on_hand: int | None
    """Number of the hand the player busted in; None for the survivors."""
    rebuys: int = 0
    add_ons: int = 0

    @property
    def profit(self) -> int:
        return self.prize - self.invested


@dataclass(frozen=True)
class TournamentResult:
    finishes: tuple[Finish, ...]
    """Ordered from the winner to the first player out."""
    prize_pool: int
    buy_in: int
    hands_played: int
    level_index: int
    """Index of the last level played."""
    level: BlindLevel
    multiplier: int | None = None
    """Prize multiplier of a Spin & Go."""
    capped: bool = False
    """Stopped by ``max_hands``: the survivors were ranked by stack."""

    @property
    def winner(self) -> Finish:
        return self.finishes[0]

    def finish_of(self, name: str) -> Finish:
        return next(finish for finish in self.finishes if finish.name == name)

    def to_dict(self) -> dict[str, object]:
        return {
            "prize_pool": self.prize_pool,
            "buy_in": self.buy_in,
            "multiplier": self.multiplier,
            "hands_played": self.hands_played,
            "level_reached": self.level_index + 1,
            "level": self.level.describe(),
            "capped": self.capped,
            "finishes": [
                {
                    "name": finish.name,
                    "place": finish.place,
                    "prize": finish.prize,
                    "invested": finish.invested,
                    "eliminated_on_hand": finish.eliminated_on_hand,
                    "rebuys": finish.rebuys,
                    "add_ons": finish.add_ons,
                }
                for finish in self.finishes
            ],
        }


@dataclass(frozen=True)
class Elimination:
    """Players knocked out by one hand, announced by the interface."""

    hand_number: int
    names: tuple[str, ...]
    place: int
    """Best place of the group (players with equal stacks share it)."""
    prizes: tuple[int, ...]
    """Prize of each player, with the prize pool at that time."""


class LevelClock:
    """Playing time of a tournament, which an explicit pause freezes.

    The time keeps running while a player thinks or is idle.
    """

    def __init__(self, time_source: Callable[[], float] = time.monotonic) -> None:
        self._time_source = time_source
        self._started = time_source()
        self._paused_at: float | None = None
        self._paused_total = 0.0

    @property
    def is_paused(self) -> bool:
        return self._paused_at is not None

    def pause(self) -> None:
        if self._paused_at is None:
            self._paused_at = self._time_source()

    def resume(self) -> None:
        if self._paused_at is not None:
            self._paused_total += self._time_source() - self._paused_at
            self._paused_at = None

    def elapsed(self) -> float:
        now = self._paused_at if self._paused_at is not None else self._time_source()

        return now - self._started - self._paused_total


@dataclass
class _Entry:
    """Running state of one player."""

    rebuys: int = 0
    add_ons: int = 0
    place: int | None = None
    eliminated_on_hand: int | None = None


@dataclass
class _PendingHand:
    """Busted players of the last hand, waiting for rebuy decisions."""

    hand_number: int
    stacks_before: dict[str, int]
    busted: list[str] = field(default_factory=list)


class Tournament:
    """A single-table tournament played by controllers (humans and bots)."""

    def __init__(
        self,
        config: TournamentConfig,
        seat_names: Sequence[str],
        controllers: Mapping[str, PlayerController],
        dealer_index: int = 0,
        deck_rng: random.Random | None = None,
        clock: LevelClock | None = None,
        multiplier: Multiplier | None = None,
        keep_hands: bool = False,
        on_hand_end: HandEndCallback | None = None,
    ) -> None:
        """Seat the players; the first hand is dealt by ``start_hand``.

        Levels advance by hands, or by ``clock`` when one is given. A
        ``multiplier`` makes the prize pool that many buy-ins (Spin & Go).
        Finished hands stay in ``session.hands`` only with ``keep_hands``
        (a human game saved with its history); simulations drop them.
        ``on_hand_end`` is called with every finished hand and the stacks at
        its start, before any rebuy or elimination (chip checks).
        """
        if not MIN_PLAYERS <= len(seat_names) <= MAX_PLAYERS:
            raise ValueError(
                f"A tournament seats {MIN_PLAYERS} to {MAX_PLAYERS} players."
            )

        if len(set(seat_names)) != len(seat_names):
            raise ValueError("Player names must be unique.")

        missing = [name for name in seat_names if name not in controllers]

        if missing:
            raise ValueError(f"Players without a controller: {', '.join(missing)}.")

        first_level = config.structure.level(0)
        players = [
            Player(name=name, stack=config.starting_stack) for name in seat_names
        ]
        self.session = GameSession(
            players=players,
            config=GameConfig(
                starting_stack=config.starting_stack,
                rebuy_stack=(
                    config.rebuys.rebuy_stack
                    if config.rebuys
                    else config.starting_stack
                ),
                small_blind=first_level.small_blind,
                big_blind=first_level.big_blind,
            ),
        )
        self.session.table.dealer_index = dealer_index % len(players)
        self.session.set_blind_level(first_level)

        self.config = config
        self.controllers = dict(controllers)
        self.clock = clock
        self.multiplier = multiplier
        self.keep_hands = keep_hands
        self.on_hand_end = on_hand_end
        self.hand: Hand | None = None
        self.hands_played = 0
        self.level_index = 0
        self.stacks_before: dict[str, int] = {}
        self.eliminations: list[Elimination] = []
        self._deck_rng = deck_rng or random.Random()
        self._entries = {name: _Entry() for name in seat_names}
        self._pending: _PendingHand | None = None
        self._add_on_open = False
        self._add_on_offered = False
        self._capped = False
        self._result: TournamentResult | None = None

    # --- State ------------------------------------------------------------

    @property
    def players(self) -> list[Player]:
        return self.session.players

    @property
    def entrants(self) -> int:
        return len(self.players)

    @property
    def level(self) -> BlindLevel:
        return self.config.structure.level(self.level_index)

    @property
    def is_hand_in_progress(self) -> bool:
        return self.hand is not None and not self.hand.finished

    @property
    def current_player(self) -> Player | None:
        if self.hand is None or self.hand.finished:
            return None

        return self.hand.current_player

    @property
    def is_waiting_for_human(self) -> bool:
        """True when the next step needs a decision from the user."""
        player = self.current_player

        if player is None:
            return False

        controller = self.controllers[player.name]

        return isinstance(controller, HumanController) and not (
            controller.has_pending_action
        )

    @property
    def is_finished(self) -> bool:
        return self._result is not None

    @property
    def result(self) -> TournamentResult:
        if self._result is None:
            raise RuntimeError("The tournament is not finished.")

        return self._result

    @property
    def prize_pool(self) -> int:
        if self.multiplier is not None:
            return self.multiplier.value * self.config.buy_in

        extra_buy_ins = sum(
            entry.rebuys + entry.add_ons for entry in self._entries.values()
        )

        return self.config.buy_in * (self.entrants + extra_buy_ins)

    @property
    def payout(self) -> PayoutStructure:
        if self.multiplier is not None:
            return self.multiplier.payout

        return self.config.payout_for(self.entrants)

    def players_left(self) -> list[Player]:
        """Players still in the tournament, including those deciding a rebuy."""
        return [
            player
            for player in self.players
            if self._entries[player.name].place is None
        ]

    def current_place(self, name: str) -> int:
        """Final place of an eliminated player, else the rank by stack."""
        entry = self._entries[name]

        if entry.place is not None:
            return entry.place

        stack = next(player.stack for player in self.players if player.name == name)

        return 1 + sum(1 for player in self.players_left() if player.stack > stack)

    def average_stack(self) -> float:
        """Average stack of the players still in; the winner's at the end."""
        left = [player for player in self.players if player.stack > 0]

        return sum(player.stack for player in left) / len(left)

    def prize_for_place(self, place: int) -> int:
        """Prize of a place with the current prize pool."""
        prizes = self.payout.prizes(self.prize_pool, self.entrants)

        return prizes[place - 1]

    def invested(self, name: str) -> int:
        entry = self._entries[name]

        if self.multiplier is not None:
            return self.config.buy_in

        return self.config.buy_in * (1 + entry.rebuys + entry.add_ons)

    def next_level_in(self) -> int | float | None:
        """Hands (or seconds with a clock) before the next level; None at the end."""
        structure = self.config.structure

        if self.clock is not None:
            return structure.seconds_until_next_level(self.clock.elapsed())

        return structure.hands_until_next_level(self.hands_played)

    # --- Rebuys and add-on ------------------------------------------------

    @property
    def rebuy_period_open(self) -> bool:
        rules = self.config.rebuys

        return rules is not None and self._next_level_index() < rules.levels

    def can_rebuy(self, name: str) -> bool:
        rules = self.config.rebuys
        entry = self._entries[name]

        if rules is None or self.is_hand_in_progress or entry.place is not None:
            return False

        if not self.rebuy_period_open:
            return False

        if rules.max_rebuys is not None and entry.rebuys >= rules.max_rebuys:
            return False

        return self._player(name).stack <= rules.threshold

    def rebuy(self, name: str) -> None:
        if not self.can_rebuy(name):
            raise RuntimeError(f"{name} cannot rebuy now.")

        rules = self.config.rebuys
        assert rules is not None
        player = self._player(name)
        player.stack += rules.rebuy_stack
        player.eliminated = False
        self._entries[name].rebuys += 1

        if self._pending is not None and name in self._pending.busted:
            self._pending.busted.remove(name)
            self._settle_pending_if_decided()

    def decline_rebuy(self, name: str) -> None:
        """A busted player who may rebuy chooses to leave the tournament."""
        if self._pending is None or name not in self._pending.busted:
            raise RuntimeError(f"{name} has no rebuy to decline.")

        self._settle_pending()

    @property
    def is_waiting_for_rebuy(self) -> bool:
        """True while a busted human may still rebuy."""
        return self._pending is not None

    def can_add_on(self, name: str) -> bool:
        rules = self.config.rebuys

        return (
            rules is not None
            and rules.add_on_stack is not None
            and self._add_on_open
            and not self.is_hand_in_progress
            and self._entries[name].place is None
            and self._entries[name].add_ons == 0
        )

    def add_on(self, name: str) -> None:
        if not self.can_add_on(name):
            raise RuntimeError(f"{name} cannot take the add-on now.")

        rules = self.config.rebuys
        assert rules is not None and rules.add_on_stack is not None
        self._player(name).stack += rules.add_on_stack
        self._entries[name].add_ons += 1

    # --- Hands ------------------------------------------------------------

    def start_hand(self, deck: Deck | None = None) -> Hand:
        """Deal the next hand at the current level.

        A busted human who has not rebought by now is eliminated. ``deck``
        replaces the next deck of the tournament's own random stream (tests).
        """
        if self.is_finished:
            raise RuntimeError("The tournament is over.")

        if self.is_hand_in_progress:
            raise RuntimeError("A hand is already in progress.")

        if self._pending is not None:
            self._settle_pending()

            if self.is_finished:
                raise RuntimeError("The tournament is over.")

        self._add_on_open = False
        self.level_index = self._next_level_index()
        self.session.set_blind_level(self.level)

        if self.hands_played > 0:
            self.session.table.move_dealer()

        self.stacks_before = {
            player.name: player.stack
            for player in self.session.get_players_with_chips()
        }
        if deck is None:
            deck = Deck(random.Random(self._deck_rng.getrandbits(64)))

        self.hand = start_hand(self.session, deck)

        if self.hand.finished:
            self._on_hand_finished()

        return self.hand

    def build_context(self, player: Player) -> DecisionContext:
        if self.hand is None:
            raise RuntimeError("No hand has been started.")

        return build_decision_context(
            hand=self.hand,
            player=player,
            big_blind=self.level.big_blind,
            game_format=GameFormat.TOURNAMENT,
        )

    def step(self) -> ActionEvent | None:
        """Play the next decision, or deal the next street."""
        hand = self.hand

        if hand is None or hand.finished:
            raise RuntimeError("No hand is in progress.")

        player = hand.current_player
        event = None

        if player is None:
            advance_hand(hand)
        else:
            action = self.controllers[player.name].choose_action(
                self.build_context(player)
            )
            event = apply_action(hand, action)

        if hand.finished:
            self._on_hand_finished()

        return event

    def play_hand(self, deck: Deck | None = None) -> Hand:
        hand = self.start_hand(deck)

        while not hand.finished:
            self.step()

        return hand

    def play_to_end(self) -> TournamentResult:
        """Play every remaining hand; only for tables with no human deciding."""
        while not self.is_finished:
            if self._pending is not None:
                self._settle_pending()
                continue

            self.play_hand()

        return self.result

    # --- End of a hand ----------------------------------------------------

    def _on_hand_finished(self) -> None:
        self.hands_played += 1

        if self.hand is not None:
            notify_hand_end(self.controllers.values(), self.hand.actions)

        if self.on_hand_end is not None and self.hand is not None:
            self.on_hand_end(self.hand, self.stacks_before)

        if not self.keep_hands:
            self.session.hands.clear()  # Millions of hands would fill the memory.

        # Bots rebuy whenever they may, busted or at the threshold.
        for player in self.players_left():
            if not self.controllers[player.name].is_human and self.can_rebuy(
                player.name
            ):
                self.rebuy(player.name)

        self._pending = _PendingHand(
            hand_number=self.hands_played,
            stacks_before=dict(self.stacks_before),
            busted=[
                player.name
                for player in self.players
                if player.stack == 0 and self._entries[player.name].place is None
            ],
        )

        # A busted human who may rebuy decides through the interface.
        if not any(self.can_rebuy(name) for name in self._pending.busted):
            self._settle_pending()

        self._open_add_on_if_due()

    def _settle_pending_if_decided(self) -> None:
        if self._pending is not None and not any(
            self.can_rebuy(name) for name in self._pending.busted
        ):
            self._settle_pending()

    def _settle_pending(self) -> None:
        """Eliminate the busted players of the last hand and end if one is left."""
        pending = self._pending
        self._pending = None

        if pending is None:
            return

        busted = [name for name in pending.busted if self._player(name).stack == 0]
        left = sum(
            1
            for player in self.players
            if self._entries[player.name].place is None and player.stack > 0
        )
        self._rank_out(busted, pending.stacks_before, first_place=left + 1)

        for name in busted:
            self._entries[name].eliminated_on_hand = pending.hand_number
            self.session.eliminate_player(self._player(name))

        if busted:
            self._announce(pending.hand_number, busted)

        if left == 1:
            self._finish()
        elif self.config.max_hands is not None and (
            self.hands_played >= self.config.max_hands
        ):
            self._capped = True
            self._finish()

    def _rank_out(
        self, names: list[str], stacks: Mapping[str, int], first_place: int
    ) -> None:
        """Give places to ``names``: bigger ``stacks`` first, equal stacks tied."""
        order = self._clockwise_from_button()
        ranked = sorted(names, key=lambda name: (-stacks.get(name, 0), order[name]))
        place = first_place

        while ranked:
            stack = stacks.get(ranked[0], 0)
            group = [name for name in ranked if stacks.get(name, 0) == stack]
            ranked = ranked[len(group) :]

            for name in group:
                self._entries[name].place = place

            place += len(group)

    def _announce(self, hand_number: int, names: list[str]) -> None:
        prizes = self.payout.prizes(self.prize_pool, self.entrants)
        order = self._clockwise_from_button()
        places = sorted({self._entries[name].place or 0 for name in names})

        for place in places:
            group = sorted(
                (n for n in names if self._entries[n].place == place),
                key=order.__getitem__,
            )
            shares = split_prizes(
                prizes[place - 1 : place - 1 + len(group)], len(group)
            )
            self.eliminations.append(
                Elimination(hand_number, tuple(group), place, tuple(shares))
            )

    def _open_add_on_if_due(self) -> None:
        rules = self.config.rebuys

        if (
            rules is None
            or rules.add_on_stack is None
            or self._add_on_offered
            or self.is_finished
            or self._next_level_index() < rules.levels
        ):
            return

        self._add_on_offered = True
        self._add_on_open = True

        for player in self.players_left():
            wants_add_on = (
                not self.controllers[player.name].is_human
                and player.stack <= self.config.starting_stack
            )

            if wants_add_on and self.can_add_on(player.name):
                self.add_on(player.name)

    def _finish(self) -> None:
        survivors = [
            player.name
            for player in self.players
            if self._entries[player.name].place is None
        ]
        stacks = {player.name: player.stack for player in self.players}
        self._rank_out(survivors, stacks, first_place=1)
        self._result = self._build_result()

    def _build_result(self) -> TournamentResult:
        prizes = self.payout.prizes(self.prize_pool, self.entrants)
        order = self._clockwise_from_button()
        by_place: dict[int, list[str]] = {}

        for name, entry in self._entries.items():
            assert entry.place is not None
            by_place.setdefault(entry.place, []).append(name)

        prize_of: dict[str, int] = {}

        for place, names in by_place.items():
            names.sort(key=order.__getitem__)
            shares = split_prizes(
                prizes[place - 1 : place - 1 + len(names)], len(names)
            )
            prize_of.update(zip(names, shares, strict=True))

        finishes = tuple(
            sorted(
                (
                    Finish(
                        name=name,
                        place=entry.place or 0,
                        prize=prize_of[name],
                        invested=self.invested(name),
                        eliminated_on_hand=entry.eliminated_on_hand,
                        rebuys=entry.rebuys,
                        add_ons=entry.add_ons,
                    )
                    for name, entry in self._entries.items()
                ),
                key=lambda finish: (finish.place, order[finish.name]),
            )
        )

        return TournamentResult(
            finishes=finishes,
            prize_pool=self.prize_pool,
            buy_in=self.config.buy_in,
            hands_played=self.hands_played,
            level_index=self.level_index,
            level=self.level,
            multiplier=self.multiplier.value if self.multiplier else None,
            capped=self._capped,
        )

    # --- Helpers ----------------------------------------------------------

    def _next_level_index(self) -> int:
        structure = self.config.structure

        if self.clock is not None:
            index = structure.level_index_for_time(self.clock.elapsed())
        else:
            index = structure.level_index_for_hand(self.hands_played)

        return max(index, self.level_index)

    def _player(self, name: str) -> Player:
        return next(player for player in self.players if player.name == name)

    def _clockwise_from_button(self) -> dict[str, int]:
        table = self.session.table

        return {
            player.name: index
            for index, player in enumerate(table.players_after(table.dealer))
        }


# --- Spin & Go --------------------------------------------------------------


@dataclass(frozen=True)
class SpinConfig:
    """A Spin & Go: three players, hyper-turbo, a random prize multiplier."""

    multipliers: MultiplierTable
    buy_in: int = 10
    structure: BlindStructure = SPIN_HYPER_TURBO
    starting_stack: int = SPIN_STARTING_STACK
    max_hands: int | None = None

    def tournament_config(self) -> TournamentConfig:
        return TournamentConfig(
            structure=self.structure,
            starting_stack=self.starting_stack,
            buy_in=self.buy_in,
            max_hands=self.max_hands,
        )


def create_spin(
    config: SpinConfig,
    seat_names: Sequence[str],
    controllers: Mapping[str, PlayerController],
    rng: random.Random,
    clock: LevelClock | None = None,
    keep_hands: bool = False,
    on_hand_end: HandEndCallback | None = None,
) -> Tournament:
    """Draw the prize multiplier, then seat the three players.

    Everything random comes from ``rng``, in this order: the multiplier, the
    first button, the decks.
    """
    if len(seat_names) != SPIN_PLAYERS:
        raise ValueError(f"A Spin & Go seats {SPIN_PLAYERS} players.")

    multiplier = config.multipliers.draw(rng)

    return Tournament(
        config=config.tournament_config(),
        seat_names=seat_names,
        controllers=controllers,
        dealer_index=rng.randrange(SPIN_PLAYERS),
        deck_rng=random.Random(rng.getrandbits(64)),
        clock=clock,
        multiplier=multiplier,
        keep_hands=keep_hands,
        on_hand_end=on_hand_end,
    )
