"""Hand histories of PokerStars and Winamax, read for the replayer (V1.1.1).

A history file holds one or more hands (a Winamax session file holds the
whole session). Each hand is dealt again through the engine with the
players, stacks, cards and decisions of the history, and checked against it:
the forced bets, the order of action, every amount, the board and the
winners. A hand is kept only when the engine plays it exactly as the site
did; the others are listed with the reason, for example:

- not No Limit Hold'em, or "run it twice";
- blinds this engine does not post: a dead blind, a blind posted out of
  position, a straddle, a dead button;
- more than 9 players dealt in.

**Unknown cards.** A history only shows your cards and the cards shown at
showdown. Every other player is given cards nobody holds, which are never
shown (``HandRecord.hidden``); a player who mucked at showdown gets the
weakest such hand, so the winner stays the same.

**Amounts.** Real-money amounts are counted in cents (0.25 € becomes 25);
tournament chips stay chips. The winnings are the engine's, before the
rake; the history's rake is part of the check.
"""

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from itertools import combinations
from pathlib import Path

from backend.poker_engine.actions import Action
from backend.poker_engine.betting import IllegalActionError, apply_action
from backend.poker_engine.blinds import AnteType, BlindLevel
from backend.poker_engine.constants import MAX_HAND_PLAYERS, ActionType, Card, Street
from backend.poker_engine.deck import Deck
from backend.poker_engine.hand import advance_hand, start_hand
from backend.poker_engine.hand_evaluator import evaluate_rank
from backend.poker_engine.models import Hand, Player
from backend.poker_engine.session import GameConfig, GameSession

from .equity import FULL_DECK
from .game_modes import GameMode
from .hand_records import HandRecord, SessionRecord
from .persistence import SessionFileError, serialize_hand
from .replay import deal_order

POKERSTARS = "PokerStars"
WINAMAX = "Winamax"
CENTS = 100

AMOUNT = r"[$€£]?\s?\d[\d.,]*\s?[$€£]?"
CARD = r"[2-9TJQKA][cdhs]"
DATE = re.compile(r"(\d{4}/\d{2}/\d{2} \d{1,2}:\d{2}:\d{2})")
SEAT = re.compile(rf"^Seat (\d+): (.+?) \(({AMOUNT})(?: in chips)?(?:,[^)]*)?\)(.*)$")
BUTTON = re.compile(r"Seat #(\d+) is the button")
MARKER = re.compile(r"^\*\*\* (.+?) \*\*\*(.*)$")
CARDS = re.compile(CARD)
DEALT = re.compile(rf"^Dealt to (.+?) \[({CARD} {CARD})\]")
UNCALLED = re.compile(rf"^Uncalled bet \(({AMOUNT})\) returned to (.+)$")
RAKE = re.compile(rf"Rake ({AMOUNT})")
BOARD = re.compile(r"^Board:? \[(.+?)\]")
SUMMARY_CARDS = re.compile(rf"(?:showed|mucked) \[({CARD} {CARD})\]")
SUMMARY_WON = re.compile(rf"(?:won|collected) \(?({AMOUNT})\)?")

STREETS = {"FLOP": Street.FLOP, "TURN": Street.TURN, "RIVER": Street.RIVER}
PREFLOP_MARKERS = ("HOLE CARDS", "PRE-FLOP", "ANTE/BLINDS", "PREFLOP")
SHOWDOWN_MARKERS = ("SHOW DOWN", "SHOWDOWN")


class UnsupportedHand(ValueError):
    """A hand the engine does not play as the site did."""


@dataclass(frozen=True)
class Decision:
    street: Street
    player: str
    kind: str
    """fold, check, call, bet or raise."""
    amount: int = 0
    """Chips added by a call or a bet; the total "raise to" of a raise."""
    all_in: bool = False


@dataclass
class ParsedHand:
    """What a history says about one hand, before the engine checks it."""

    site: str
    hand_id: str
    started: datetime | None = None
    tournament: bool = False
    button_seat: int = 0
    seats: list[tuple[int, str, int]] = field(default_factory=list)
    small_blind: int = 0
    big_blind: int = 0
    posts: list[tuple[str, str, int]] = field(default_factory=list)
    """(player, post_sb / post_bb / post_ante, amount)."""
    decisions: list[Decision] = field(default_factory=list)
    board: list[Card] = field(default_factory=list)
    known: dict[str, tuple[Card, Card]] = field(default_factory=dict)
    hero: str | None = None
    won: Counter[str] = field(default_factory=Counter)
    returned: Counter[str] = field(default_factory=Counter)
    rake: int = 0
    problem: str | None = None
    """The first thing read that this engine does not play."""

    @property
    def dealt_in(self) -> list[str]:
        """The players with an action: everyone dealt in posts or acts."""
        acting = {name for name, _, _ in self.posts}
        acting |= {decision.player for decision in self.decisions}

        return [name for _, name, _ in self.seats if name in acting]


# --- Files ------------------------------------------------------------------------


def read_hand_history_file(path: Path) -> SessionRecord:
    """The hands of a PokerStars or Winamax history file, ready to replay.

    Raises ``SessionFileError`` when the file holds no hand of either site.
    """
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise SessionFileError(f"{path.name} cannot be read: {error}") from error

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    blocks = split_hands(text)

    if not blocks:
        raise SessionFileError(f"{path.name} holds no PokerStars or Winamax hand.")

    return import_hands(path, blocks)


def split_hands(text: str) -> list[list[str]]:
    """The lines of every hand of a history, in order."""
    hands: list[list[str]] = []

    for line in text.splitlines():
        line = line.strip()

        if _is_hand_start(line):
            hands.append([line])
        elif hands and line:
            hands[-1].append(line)

    return hands


def _is_hand_start(line: str) -> bool:
    return (line.startswith(POKERSTARS) and " Hand #" in line) or line.startswith(
        "Winamax Poker - "
    )


def import_hands(path: Path, blocks: Sequence[Sequence[str]]) -> SessionRecord:
    records: list[HandRecord] = []
    notes: list[str] = []
    parsed_hands = [parse_hand(lines) for lines in blocks]

    for parsed in parsed_hands:
        try:
            record = build_record(parsed, number=len(records) + 1)
        except UnsupportedHand as error:
            notes.append(f"Hand {parsed.hand_id}: {error}")
            continue

        records.append(record)

    heroes = Counter(parsed.hero for parsed in parsed_hands if parsed.hero)
    names = list(
        dict.fromkeys(name for parsed in parsed_hands for _, name, _ in parsed.seats)
    )
    first = parsed_hands[0]

    return SessionRecord(
        path=path,
        started=first.started or datetime.fromtimestamp(path.stat().st_mtime),
        mode=(
            GameMode.TOURNAMENT
            if any(parsed.tournament for parsed in parsed_hands)
            else GameMode.CASH
        ),
        human=heroes.most_common(1)[0][0] if heroes else (names or ["?"])[0],
        seat_names=tuple(names),
        hands=tuple(records),
        finish=None,
        source=first.site,
        notes=tuple(notes),
    )


# --- Reading one hand -------------------------------------------------------------


def parse_hand(lines: Sequence[str]) -> ParsedHand:
    """Read the lines of one hand; what cannot be played is in ``problem``."""
    header = lines[0]
    site = POKERSTARS if header.startswith(POKERSTARS) else WINAMAX
    hand_id = re.search(r"(?:Hand #|HandId: #)([\w-]+)", header)
    parsed = ParsedHand(site=site, hand_id=hand_id.group(1) if hand_id else "?")
    date = DATE.search(header)
    parsed.started = (
        datetime.strptime(date.group(1), "%Y/%m/%d %H:%M:%S") if date else None
    )
    parsed.tournament = "Tournament" in header

    try:
        scale = _read_header(parsed, header)
        _read_body(parsed, lines[1:], scale)
    except (UnsupportedHand, InvalidOperation, ValueError) as error:
        parsed.problem = parsed.problem or str(error)

    return parsed


def _read_header(parsed: ParsedHand, header: str) -> int:
    """Read the game and the blinds; returns the scale of the amounts."""
    game = header.lower().replace("'", "")

    if "holdem no limit" not in game:
        raise UnsupportedHand("only No Limit Hold'em hands can be replayed")

    blinds = re.search(r"\(([^()]*/[^()]*)\)", header)

    if blinds is None:
        raise UnsupportedHand("the blinds of the hand are not in its header")

    parts = [part.strip() for part in blinds.group(1).split("/")]
    money = any(re.search(r"[$€£.]", part) for part in parts)
    scale = CENTS if money else 1
    amounts = [_amount(part.split()[0], scale) for part in parts]
    parsed.small_blind, parsed.big_blind = amounts[-2], amounts[-1]

    return scale


def _read_body(parsed: ParsedHand, lines: Sequence[str], scale: int) -> None:
    street = Street.PREFLOP
    in_summary = False
    seats_open = True
    names: list[str] = []
    collected_in_body = False

    for line in lines:
        if seats_open and (seat := SEAT.match(line)):
            number, name, stack, rest = seat.groups()

            if "out of hand" not in rest and "sitting out" not in rest:
                parsed.seats.append((int(number), name, _amount(stack, scale)))

            names.append(name)
            continue

        if button := BUTTON.search(line):
            parsed.button_seat = int(button.group(1))
            continue

        seats_open = seats_open and not names
        names_by_length = sorted(names, key=len, reverse=True)

        if marker := MARKER.match(line):
            title = marker.group(1).upper()

            if title == "SUMMARY":
                in_summary = True
            elif "FIRST" in title or "SECOND" in title:
                raise UnsupportedHand("run it twice is not played by this engine")
            elif title in STREETS:
                street = STREETS[title]
                parsed.board = _cards(marker.group(2))
            elif title not in PREFLOP_MARKERS + SHOWDOWN_MARKERS:
                raise UnsupportedHand(f"unknown section “{title}”")

            continue

        if in_summary:
            _read_summary_line(parsed, line, names_by_length, scale, collected_in_body)
            continue

        if dealt := DEALT.match(line):
            hero = parsed.hero = dealt.group(1)
            first, second = _cards(dealt.group(2))
            parsed.known[hero] = (first, second)
            continue

        if uncalled := UNCALLED.match(line):
            parsed.returned[uncalled.group(2)] += _amount(uncalled.group(1), scale)
            continue

        split = _split_actor(line, names_by_length)

        if split is not None:
            actor, rest = split
            collected_in_body |= _read_action(parsed, street, actor, rest, scale)


def _split_actor(line: str, names: Iterable[str]) -> tuple[str, str] | None:
    """(player, rest of the line): "Hero: calls 2" or "Hero calls 2"."""
    for name in names:
        for separator in (": ", " "):
            if line.startswith(name + separator):
                return name, line[len(name) + len(separator) :]

    return None


def _read_action(
    parsed: ParsedHand, street: Street, actor: str, rest: str, scale: int
) -> bool:
    """Read a player's line; returns True when it is a "collected" line."""

    def amounts() -> list[int]:
        return [_amount(token, scale) for token in re.findall(AMOUNT, rest)]

    all_in = "all-in" in rest

    if rest.startswith("posts"):
        parsed.posts.append((actor, _post_kind(rest), amounts()[0]))
    elif rest.startswith("folds"):
        parsed.decisions.append(Decision(street, actor, "fold"))
    elif rest.startswith("checks"):
        parsed.decisions.append(Decision(street, actor, "check"))
    elif rest.startswith(("calls", "bets")):
        kind = rest.split()[0][:-1]
        parsed.decisions.append(Decision(street, actor, kind, amounts()[0], all_in))
    elif rest.startswith("raises"):
        decision = Decision(street, actor, "raise", amounts()[-1], all_in)
        parsed.decisions.append(decision)
    elif rest.startswith("shows"):
        cards = _cards(rest)

        if len(cards) >= 2:
            parsed.known[actor] = (cards[0], cards[1])
    elif rest.startswith("collected"):
        parsed.won[actor] += amounts()[0]
        return True

    return False


def _post_kind(rest: str) -> str:
    if "out of position" in rest or "&" in rest or "dead" in rest:
        raise UnsupportedHand("a blind posted out of turn (dead or missed blind)")

    if rest.startswith("posts small blind") or rest.startswith("posts the small blind"):
        return "post_sb"

    if rest.startswith("posts big blind") or rest.startswith("posts the big blind"):
        return "post_bb"

    if "ante" in rest:
        return "post_ante"

    raise UnsupportedHand(f"a post this engine does not play (“{rest}”)")


def _read_summary_line(
    parsed: ParsedHand,
    line: str,
    names: Iterable[str],
    scale: int,
    collected_in_body: bool,
) -> None:
    if line.startswith("Total pot"):
        rake = RAKE.search(line)
        parsed.rake = _amount(rake.group(1), scale) if rake else 0
        return

    if board := BOARD.match(line):
        parsed.board = _cards(board.group(1))
        return

    if not line.startswith("Seat "):
        return

    split = _split_actor(line.split(": ", 1)[-1], names)

    if split is None:
        return

    name, rest = split

    if shown := SUMMARY_CARDS.search(rest):
        first, second = _cards(shown.group(1))
        parsed.known[name] = (first, second)

    if not collected_in_body and (won := SUMMARY_WON.search(rest)):
        parsed.won[name] += _amount(won.group(1), scale)


def _cards(text: str) -> list[Card]:
    """The cards written in a history ("As Kd"), as engine cards ("AS")."""
    return [card[0] + card[1].upper() for card in CARDS.findall(text)]


def _amount(token: str, scale: int) -> int:
    """An amount of the history as engine chips: "$0.25" in cents is 25."""
    digits = re.sub(r"[^\d.]", "", token.replace(",", ""))
    value = Decimal(digits) * scale

    if value != value.to_integral_value():
        raise UnsupportedHand(f"the amount {token} is smaller than a chip")

    return int(value)


# --- Playing it through the engine ------------------------------------------------


def build_record(parsed: ParsedHand, number: int) -> HandRecord:
    """The hand played again by the engine; raises ``UnsupportedHand``."""
    if parsed.problem:
        raise UnsupportedHand(parsed.problem)

    names = parsed.dealt_in

    if not 2 <= len(names) <= MAX_HAND_PLAYERS:
        raise UnsupportedHand(
            f"{len(names)} players dealt in: the engine plays 2 to {MAX_HAND_PLAYERS}"
        )

    dealer = next(
        (name for seat, name, _ in parsed.seats if seat == parsed.button_seat), None
    )

    if dealer not in names:
        raise UnsupportedHand("the button was not dealt in (dead button)")

    stacks = {name: stack for _, name, stack in parsed.seats}
    session = GameSession(
        players=[Player(name=name, stack=stacks[name]) for name in names],
        config=GameConfig(),
    )
    session.set_blind_level(_blind_level(parsed))
    session.table.dealer_index = names.index(dealer)
    hole_cards = _hole_cards(parsed, names)

    try:
        deck = Deck.stacked(deal_order(names, dealer, hole_cards, parsed.board))
        hand = start_hand(session, deck=deck)
    except (ValueError, RuntimeError) as error:
        raise UnsupportedHand(f"the hand cannot be dealt: {error}") from error

    posted = Counter((e.player, e.action, e.amount) for e in hand.actions)

    if posted != Counter(parsed.posts):
        raise UnsupportedHand(
            "the blinds and antes are not posted as this engine posts them"
        )

    for decision in parsed.decisions:
        _play(hand, decision)

    while not hand.finished:
        if hand.current_player is not None:
            raise UnsupportedHand(f"{hand.current_player.name} still has to act")

        advance_hand(hand)

    _check_end(parsed, hand)
    record = HandRecord.from_dict(serialize_hand(hand, number))
    hidden = frozenset(name for name in names if name not in parsed.known)

    return replace(record, hidden=hidden, hand_id=f"{parsed.site} #{parsed.hand_id}")


def _blind_level(parsed: ParsedHand) -> BlindLevel:
    antes = {
        (name, amount) for name, kind, amount in parsed.posts if kind == "post_ante"
    }
    big_blind = next(
        (name for name, kind, _ in parsed.posts if kind == "post_bb"), None
    )

    if not antes:
        ante, ante_type = 0, AnteType.CLASSIC
    elif {name for name, _ in antes} == {big_blind} and len(parsed.dealt_in) > 2:
        ante, ante_type = max(amount for _, amount in antes), AnteType.BIG_BLIND
    else:
        ante, ante_type = max(amount for _, amount in antes), AnteType.CLASSIC

    try:
        return BlindLevel(parsed.small_blind, parsed.big_blind, ante, ante_type)
    except ValueError as error:
        raise UnsupportedHand(f"blinds not played by this engine: {error}") from error


def _hole_cards(parsed: ParsedHand, names: list[str]) -> dict[str, tuple[Card, Card]]:
    """The known cards, and cards nobody holds for everyone else.

    A player still in the hand at the end who did not show gets the weakest
    hand left on the board, so they lose as they did.
    """
    cards = {name: parsed.known[name] for name in names if name in parsed.known}
    used = {card for pair in cards.values() for card in pair} | set(parsed.board)
    folded = {d.player for d in parsed.decisions if d.kind == "fold"}
    unknown = [name for name in names if name not in cards]

    for name in sorted(unknown, key=lambda name: name in folded):
        left = [card for card in FULL_DECK if card not in used]

        if name not in folded and len(parsed.board) == 5:
            pair = min(
                combinations(left, 2),
                key=lambda pair: evaluate_rank([*pair, *parsed.board]),
            )
        else:
            pair = (left[0], left[1])

        cards[name] = (pair[0], pair[1])
        used |= set(pair)

    return cards


def _play(hand: Hand, decision: Decision) -> None:
    while hand.current_player is None and not hand.finished:
        advance_hand(hand)

    player = hand.current_player

    if hand.finished or player is None:
        raise UnsupportedHand("the hand ends before the history does")

    if hand.street != decision.street or player.name != decision.player:
        raise UnsupportedHand(
            f"{decision.player} acts out of turn for this engine ({hand.street})"
        )

    bet_before = player.current_bet
    action, added = _action(decision, bet_before)

    try:
        event = apply_action(hand, action)
    except IllegalActionError as error:
        raise UnsupportedHand(f"{decision.player}: {error}") from error

    if added is not None and event.amount != added:
        raise UnsupportedHand(f"{decision.player} does not put in the chips recorded")


def _action(decision: Decision, bet_before: int) -> tuple[Action, int | None]:
    """The engine action, and the chips it must add (None: any, an all-in)."""
    match decision.kind:
        case "fold":
            return Action(ActionType.FOLD), 0
        case "check":
            return Action(ActionType.CHECK), 0
        case "call":
            return Action(ActionType.CALL), decision.amount
        case "bet" if decision.all_in:
            return Action(ActionType.ALL_IN), decision.amount
        case "bet":
            raise_to = bet_before + decision.amount
            return Action(ActionType.RAISE, raise_to), decision.amount
        case _ if decision.all_in:
            return Action(ActionType.ALL_IN), decision.amount - bet_before
        case _:
            raise_to = decision.amount
            return Action(ActionType.RAISE, raise_to), raise_to - bet_before


def _check_end(parsed: ParsedHand, hand: Hand) -> None:
    if parsed.board and list(hand.community_cards) != parsed.board:
        raise UnsupportedHand("the board is not the one of the history")

    engine = {name: amount for name, amount in hand.payouts.items() if amount > 0}
    winners = {name for name, amount in parsed.won.items() if amount > 0}
    refunded = {name for name, amount in parsed.returned.items() if amount > 0}
    paid = sum(parsed.won.values()) + sum(parsed.returned.values()) + parsed.rake
    totals = {paid}

    if not refunded:
        # Without "Uncalled bet" lines, the chips nobody called may be counted
        # in what the biggest contributor collected: the engine pays them too.
        players = sorted(hand.table.players, key=lambda p: -p.total_contribution)
        uncalled = players[0].total_contribution - players[1].total_contribution
        refunded = {players[0].name} if uncalled else set()
        totals.add(paid + uncalled)

    if (
        not winners <= set(engine)
        or not set(engine) <= winners | refunded
        or sum(engine.values()) not in totals
    ):
        raise UnsupportedHand("the winnings are not those of the history")
