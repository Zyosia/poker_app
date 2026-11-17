"""PokerStars and Winamax hand histories written from recorded hands (tests).

The import of other sites' histories is tested by writing the hands this
engine played in their formats, reading them back, and comparing.
"""

from backend.application.hand_records import FORCED_ACTIONS, HandRecord
from backend.poker_engine.constants import ActionType, Street
from backend.poker_engine.models import ActionEvent

DATE = "2026/11/17 10:00:00"
POKERSTARS_FILE = """﻿PokerStars Hand #241234567890:  Hold'em No Limit ($0.01/$0.02 USD) - 2022/11/05 10:12:13 CET [2022/11/05 4:12:13 ET]
Table 'Acamar IV' 6-max Seat #6 is the button
Seat 1: Alice ($2.11 in chips)
Seat 2: Bob Smith ($1.98 in chips)
Seat 3: Hero ($2 in chips)
Seat 5: Eve ($3.40 in chips) is sitting out
Seat 6: Dan ($1.50 in chips)
Alice: posts small blind $0.01
Bob Smith: posts big blind $0.02
*** HOLE CARDS ***
Dealt to Hero [9c 9d]
Hero: raises $0.04 to $0.06
Dan: folds
Dan said, "nice table 1.5"
Alice: folds
Bob Smith: calls $0.04
*** FLOP *** [2c 7d 9h]
Bob Smith: checks
Hero: bets $0.08
Bob Smith: raises $0.16 to $0.24
Hero: calls $0.16
*** TURN *** [2c 7d 9h] [Qs]
Bob Smith: checks
Hero: checks
*** RIVER *** [2c 7d 9h Qs] [3d]
Bob Smith: checks
Hero: bets $0.50
Bob Smith: calls $0.50
*** SHOW DOWN ***
Hero: shows [9c 9d] (three of a kind, Nines)
Bob Smith: mucks hand
Hero collected $1.54 from pot
*** SUMMARY ***
Total pot $1.61 | Rake $0.07
Board [2c 7d 9h Qs 3d]
Seat 1: Alice (small blind) folded before Flop
Seat 2: Bob Smith (big blind) mucked
Seat 3: Hero showed [9c 9d] and won ($1.54) with three of a kind, Nines
Seat 6: Dan (button) folded before Flop (didn't bet)



PokerStars Hand #241234567891:  Hold'em No Limit ($0.01/$0.02 USD) - 2022/11/05 10:13:02 CET [2022/11/05 4:13:02 ET]
Table 'Acamar IV' 6-max Seat #1 is the button
Seat 1: Alice ($2.10 in chips)
Seat 2: Bob Smith ($1.18 in chips)
Seat 3: Hero ($2.81 in chips)
Seat 5: Eve ($3.40 in chips) is sitting out
Seat 6: Dan ($1.50 in chips)
Bob Smith: posts small blind $0.01
Hero: posts big blind $0.02
*** HOLE CARDS ***
Dealt to Hero [7s 2d]
Dan: raises $0.04 to $0.06
Alice: folds
Bob Smith: folds
Hero: folds
Uncalled bet ($0.04) returned to Dan
Dan collected $0.05 from pot
Dan: doesn't show hand
*** SUMMARY ***
Total pot $0.05 | Rake $0
Seat 6: Dan collected ($0.05)



PokerStars Hand #241234567892:  Hold'em No Limit ($0.01/$0.02 USD) - 2022/11/05 10:14:00 CET [2022/11/05 4:14:00 ET]
Table 'Acamar IV' 6-max Seat #2 is the button
Seat 1: Alice ($2.10 in chips)
Seat 2: Bob Smith ($1.17 in chips)
Seat 3: Hero ($2.79 in chips)
Seat 5: Eve ($3.40 in chips)
Seat 6: Dan ($1.53 in chips)
Hero: posts small blind $0.01
Dan: posts big blind $0.02
Eve: posts small & big blinds $0.03
*** HOLE CARDS ***
Dealt to Hero [Ac Ad]
*** SUMMARY ***



PokerStars Hand #241234567893:  Omaha Pot Limit ($0.01/$0.02 USD) - 2022/11/05 10:15:00 CET [2022/11/05 4:15:00 ET]
Table 'Acamar IV' 6-max Seat #3 is the button
Seat 1: Alice ($2.10 in chips)
Seat 3: Hero ($2.79 in chips)
"""

WINAMAX_FILE = """Winamax Poker - Tournament "Freeroll" buyIn: 0€ + 0€ level: 3 - HandId: #1234567-89-1600000000 - Holdem no limit (10/50/100) - 2024/03/10 20:15:00 UTC
Table: 'Freeroll(123456)#004' 9-max (real money) Seat #7 is the button
Seat 1: Joueur Un (10000)
Seat 2: Bea (8000)
Seat 3: Hero (12000)
Seat 4: Max (9500)
Seat 5: Zoe (7000)
Seat 6: Ugo (11000)
Seat 7: Lou (10000)
*** ANTE/BLINDS ***
Joueur Un posts ante 10
Bea posts ante 10
Hero posts ante 10
Max posts ante 10
Zoe posts ante 10
Ugo posts ante 10
Lou posts ante 10
Joueur Un posts small blind 50
Bea posts big blind 100
Dealt to Hero [Kh Kc]
*** PRE-FLOP ***
Hero raises 150 to 250
Max folds
Zoe folds
Ugo calls 250
Lou folds
Joueur Un folds
Bea folds
*** FLOP *** [Td 4s 2h]
Hero bets 400
Ugo calls 400
*** TURN *** [Td 4s 2h][7c]
Hero checks
Ugo checks
*** RIVER *** [Td 4s 2h 7c][Ks]
Hero bets 900
Ugo folds
Hero collected 1520 from pot
*** SUMMARY ***
Total pot 1520 | No rake
Board: [Td 4s 2h 7c Ks]
Seat 3: Hero won 1520
"""

POST_TEXTS = {
    "post_sb": "posts small blind",
    "post_bb": "posts big blind",
    "post_ante": "posts the ante",
}


def pokerstars_text(
    record: HandRecord, hero: str, hand_id: int = 1, money: bool = False
) -> str:
    return HistoryWriter(record, hero, money, winamax=False).write(hand_id)


def winamax_text(
    record: HandRecord, hero: str, hand_id: int = 1, money: bool = False
) -> str:
    return HistoryWriter(record, hero, money, winamax=True).write(hand_id)


class HistoryWriter:
    def __init__(
        self, record: HandRecord, hero: str, money: bool, winamax: bool
    ) -> None:
        assert record.seats is not None
        self.record = record
        self.seats = record.seats
        self.hero = hero
        self.money = money
        self.winamax = winamax
        self.lines: list[str] = []

    def amount(self, chips: int) -> str:
        if not self.money:
            return str(chips)

        value = f"{chips / 100:.2f}"

        return f"{value}€" if self.winamax else f"${value}"

    def say(self, name: str, text: str) -> None:
        self.lines.append(f"{name} {text}" if self.winamax else f"{name}: {text}")

    def write(self, hand_id: int) -> str:
        record = self.record
        level = record.blind_level
        blinds = f"{self.amount(level.small_blind)}/{self.amount(level.big_blind)}"
        button = next(i for i, s in enumerate(self.seats, 1) if s.name == record.dealer)

        if self.winamax:
            game = "CashGame" if self.money else 'Tournament "Test" buyIn: 1€ level: 1'
            self.lines += [
                f"Winamax Poker - {game} - HandId: #{hand_id}-1-1 - "
                f"Holdem no limit ({blinds}) - {DATE} UTC",
                f"Table: 'Test' 9-max (real money) Seat #{button} is the button",
            ]
        else:
            game = "" if self.money else "Tournament #99, $1+$0.10 USD "
            level_text = "" if self.money else "- Level I "
            currency = " USD" if self.money else ""
            self.lines += [
                f"PokerStars Hand #{hand_id}: {game}Hold'em No Limit "
                f"{level_text}({blinds}{currency}) - {DATE} ET",
                f"Table 'Test' 9-max Seat #{button} is the button",
            ]

        for number, seat in enumerate(self.seats, 1):
            chips = "" if self.winamax else " in chips"
            self.lines.append(
                f"Seat {number}: {seat.name} ({self.amount(seat.stack)}{chips})"
            )

        self._write_actions()
        self._write_end()

        return "\n".join(self.lines) + "\n"

    def _write_actions(self) -> None:
        record = self.record
        stacks = {seat.name: seat.stack for seat in self.seats}
        boards = {street.street: street.community_cards for street in record.streets}
        streets = iter(street for street in Street if street in boards)
        current = next(streets)
        bet = 0

        if self.winamax:
            self.lines.append("*** ANTE/BLINDS ***")

        for event in record.actions:
            if event.action in FORCED_ACTIONS:
                stacks[event.player] -= event.amount
                bet = max(bet, event.current_bet_after)
                self.say(
                    event.player,
                    f"{POST_TEXTS[event.action]} {self.amount(event.amount)}",
                )
                continue

            if current == Street.PREFLOP and not any(
                line.startswith("Dealt to") for line in self.lines
            ):
                self._deal()

            while event.street != current:
                current = next(streets)
                self._marker(current, boards)
                bet = 0

            stacks[event.player] -= event.amount
            all_in = " and is all-in" if stacks[event.player] == 0 else ""
            self.say(event.player, self._action_text(event, bet) + all_in)
            bet = event.current_bet_after

        if not any(line.startswith("Dealt to") for line in self.lines):
            self._deal()

        for street in streets:
            self._marker(street, boards)

    def _deal(self) -> None:
        if not self.winamax:
            self.lines.append("*** HOLE CARDS ***")

        cards = self.record.hole_cards(self.hero)

        if cards:
            self.lines.append(f"Dealt to {self.hero} [{' '.join(_cards(cards))}]")

        if self.winamax:
            self.lines.append("*** PRE-FLOP ***")

    def _marker(self, street: Street, boards: dict) -> None:
        board = _cards(boards[street])
        old, new = board[:-1] if street != Street.FLOP else board, board[-1:]

        if street == Street.FLOP:
            text = f"[{' '.join(board)}]"
        elif self.winamax:
            text = f"[{' '.join(old)}][{' '.join(new)}]"
        else:
            text = f"[{' '.join(old)}] [{' '.join(new)}]"

        self.lines.append(f"*** {street} *** {text}")

    def _action_text(self, event: ActionEvent, bet: int) -> str:
        if event.action == ActionType.FOLD:
            return "folds"

        if event.action == ActionType.CHECK:
            return "checks"

        if event.action == ActionType.CALL:
            return f"calls {self.amount(event.amount)}"

        if bet == 0:
            return f"bets {self.amount(event.amount)}"

        return (
            f"raises {self.amount(event.bet_after - bet)} "
            f"to {self.amount(event.bet_after)}"
        )

    def _write_end(self) -> None:
        record = self.record

        if record.showdown:
            self.lines.append("*** SHOW DOWN ***")

            for name, evaluation in record.showdown.items():
                cards = record.hole_cards(name) or ()
                self.say(name, f"shows [{' '.join(_cards(cards))}] ({evaluation.name})")

        for name, amount in record.payouts.items():
            if amount > 0:
                self.lines.append(f"{name} collected {self.amount(amount)} from pot")

        rake = "No rake" if self.winamax else f"Rake {self.amount(0)}"
        self.lines += [
            "*** SUMMARY ***",
            f"Total pot {self.amount(record.pot)} | {rake}",
        ]

        if record.board:
            separator = ": " if self.winamax else " "
            self.lines.append(f"Board{separator}[{' '.join(_cards(record.board))}]")


def _cards(cards) -> list[str]:
    """ "AS" (engine) as "As" (history)."""
    return [card[0] + card[1].lower() for card in cards]
