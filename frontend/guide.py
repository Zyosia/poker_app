"""The content of the Guide window: the application, the bots, the terms.

Text only, so the window (``ui/guide_window.py``) stays a simple layout and
the content is easy to keep up to date. The bot entries are keyed like
``backend.bots.factory.BOT_TYPES``; a test checks that every bot has one.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    """A heading and its paragraphs (simple rich text: <b>, <i>)."""

    title: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    intro: str
    topics: tuple[Topic, ...] = ()


TRAITS = ("Hands played", "Aggression", "Bluffs", "Calls down", "Strength")
"""The meters of each bot card, from 1 (very little) to 5 (a lot)."""
MAX_LEVEL = 5


@dataclass(frozen=True)
class BotGuide:
    key: str
    nickname: str
    """The style in a few words."""
    portrait: str
    """How it plays, for someone new to poker."""
    traits: tuple[int, int, int, int, int]
    """One level per entry of ``TRAITS``."""
    how_to_beat: str


BOT_GUIDES: dict[str, BotGuide] = {
    guide.key: guide
    for guide in (
        BotGuide(
            key="nit",
            nickname="Very tight, passive",
            portrait=(
                "Plays very few hands, only the best ones, and prefers calling to "
                "raising. It almost never bluffs: when a Nit bets big, it has it."
            ),
            traits=(1, 2, 1, 1, 2),
            how_to_beat=(
                "Steal its blinds often, it gives them up. Fold to its raises unless "
                "your hand is very strong, and never pay off its big bets."
            ),
        ),
        BotGuide(
            key="tag",
            nickname="Tight-aggressive",
            portrait=(
                "The solid regular: few hands, played hard. It raises rather than "
                "calls, and bets the flop after raising before it."
            ),
            traits=(2, 4, 2, 2, 4),
            how_to_beat=(
                "Respect its re-raises. When it checks it is often weak: bet. It "
                "folds to pressure when it misses the flop."
            ),
        ),
        BotGuide(
            key="lag",
            nickname="Loose-aggressive",
            portrait=(
                "Plays many hands and keeps the pressure on with bets and raises. "
                "Hard to read: it can hold anything."
            ),
            traits=(4, 4, 3, 3, 4),
            how_to_beat=(
                "Call it down more often with good hands, re-raise it with strong "
                "ones, and let it bluff into you."
            ),
        ),
        BotGuide(
            key="station",
            nickname="Loose-passive",
            portrait=(
                "The calling station calls almost anything and rarely raises. It "
                "hates to fold, whatever the board."
            ),
            traits=(5, 1, 1, 5, 1),
            how_to_beat=(
                "Never bluff it: it calls. Bet your good hands for value, street "
                "after street. A raise from it means a very strong hand."
            ),
        ),
        BotGuide(
            key="maniac",
            nickname="Very loose, very aggressive",
            portrait=(
                "Bets and raises constantly, with any two cards. Huge pots and big "
                "swings, both ways."
            ),
            traits=(5, 5, 5, 4, 1),
            how_to_beat=(
                "Wait for a good hand and let it bet for you. Call more, bluff "
                "less, and expect to play big pots."
            ),
        ),
        BotGuide(
            key="basic",
            nickname="Balanced, simple",
            portrait=(
                "The original bot: plays its hand strength against the pot odds, "
                "with the occasional bluff. Average at everything."
            ),
            traits=(3, 3, 2, 3, 2),
            how_to_beat=(
                "Bet your good hands and fold the weak ones to its raises: it "
                "plays straightforwardly."
            ),
        ),
        BotGuide(
            key="shark",
            nickname="Plays by the numbers",
            portrait=(
                "The V2.0 strategy bot. Before the flop it follows charts by "
                "position. After it, it works out each opponent's <i>range</i> "
                "from their actions, deals hundreds of random showdowns against "
                "those ranges (<i>Monte Carlo</i>) and takes the action with the "
                "best <i>expected value</i>. In tournaments it watches its "
                "<i>M ratio</i>, and heads-up with a short stack it plays the "
                "push/fold equilibrium solved by <i>CFR</i>."
            ),
            traits=(2, 4, 3, 2, 5),
            how_to_beat=(
                "The toughest opponent with the Adaptive. Play tight, use your "
                "position, and avoid marginal spots: it seldom makes a big mistake."
            ),
        ),
        BotGuide(
            key="adaptive",
            nickname="Learns and exploits",
            portrait=(
                "A Shark that takes notes. It tracks how often each player plays a "
                "hand (VPIP), raises (PFR), bets or calls (aggression) and folds to "
                "a bet, and adjusts: it bluffs the players who fold too much, bets "
                "thinner for value against calling stations, steals more from "
                "tight blinds and expects bluffs from aggressive players."
            ),
            traits=(3, 4, 3, 2, 5),
            how_to_beat=(
                "Change gears: after a few dozen hands it knows your habits, so a "
                "player who always plays the same way is the easiest to exploit."
            ),
        ),
        BotGuide(
            key="random",
            nickname="Anything goes",
            portrait=(
                "Picks any legal action at random, raises of any size included. "
                "Useful as a test opponent, not as a challenge."
            ),
            traits=(4, 3, 3, 3, 1),
            how_to_beat="Play solid poker: it gives its chips away.",
        ),
    )
}

ARENA_MEASURES: dict[str, tuple[float, float, float]] = {
    "nit": (4, 1, 0.70),
    "tag": (12, 7, 2.27),
    "lag": (25, 17, 3.59),
    "station": (60, 1, 0.03),
    "maniac": (77, 54, 5.05),
    "basic": (15, 2, 0.54),
    "shark": (11, 7, 5.43),
    "adaptive": (16, 10, 4.84),
    "random": (75, 56, 2.36),
}
"""VPIP %, PFR % and aggression factor of each bot, measured in the Bot
Arena: every style at one 9-seat table, 18,000 duplicate hands (seed
20261118, ``python -m backend.simulation run --seats nit,tag,lag,station,
maniac,basic,shark,adaptive,random --duplicate``)."""

ARENA_MEASURE_NOTE = (
    "The figures come from the Bot Arena: every style at one 9-seat table, over "
    "18,000 hands. At a full table everyone plays fewer hands than heads-up or "
    "6-max; the Shark and the Adaptive bet and raise far more than they call, "
    "hence their high aggression factor."
)


SECTIONS: tuple[Section, ...] = (
    Section(
        key="welcome",
        title="Welcome",
        intro=(
            "A No Limit Texas Hold'em poker room on your computer, against bots "
            "with styles of their own. Everything is offline and the money is "
            "fictional: you start with a bankroll of 100,000."
        ),
        topics=(
            Topic(
                "Getting started",
                (
                    "<b>1.</b> Pick a mode on the main menu: <b>Cash Game</b> to sit "
                    "down for as long as you like, <b>Tournament</b> or <b>Spin & "
                    "Go</b> to play until one player holds every chip.",
                    "<b>2.</b> Choose your opponents: how many, and the play style "
                    "of each. The <b>?</b> button next to the styles opens the "
                    "<b>Bot styles</b> page of this guide.",
                    "<b>3.</b> Press <b>Play</b>. The table opens in a window of its "
                    "own; open other modes from the main menu to play several "
                    "tables at once.",
                ),
            ),
            Topic(
                "New to poker?",
                (
                    "Each player gets two hidden cards; five cards are dealt face "
                    "up in the middle, shared by everyone (the flop, the turn and "
                    "the river). The best five-card hand wins the pot, unless "
                    "everyone else folds before.",
                    "Start against the <b>Calling Station</b> or the <b>Nit</b>, the "
                    "easiest styles to read, then try the <b>Shark</b>. The "
                    "<b>Poker terms</b> page explains the vocabulary.",
                ),
            ),
        ),
    ),
    Section(
        key="modes",
        title="Game modes",
        intro="Five cards on the main menu, one per mode.",
        topics=(
            Topic(
                "♠ Cash Game",
                (
                    "You against 1 to 8 bots, from heads-up to a full-ring table of "
                    "9. A seat is bought for 40 to 100 big blinds, paid from the "
                    "bankroll and returned to it when you leave. Rebuy when you run "
                    "out of chips, or <b>top up</b> between hands (automatically if "
                    "you like); bots rebuy too, so the table stays full.",
                    "With the <b>straddle</b> option, the player under the gun puts "
                    "in two big blinds every hand and acts last before the flop.",
                ),
            ),
            Topic(
                "♣ Tournament",
                (
                    "Everyone starts with the same stack; the blinds rise level "
                    "after level until one player holds every chip. Several blind "
                    "structures, rebuys and add-on, and prizes for the best places.",
                ),
            ),
            Topic(
                "♥ Spin & Go",
                (
                    "A fast three-player tournament. Before it starts, a random "
                    "multiplier sets the prize: usually twice the buy-in, sometimes "
                    "much more.",
                ),
            ),
            Topic(
                "♦ Bot Arena",
                (
                    "Bots against bots: pick a table of styles and thousands of "
                    "hands, then compare their win rates, VPIP, aggression and "
                    "more. <b>Watch</b> mode shows the hands one by one with every "
                    "card face up. Tournaments and Spin & Go can be simulated too.",
                ),
            ),
            Topic(
                "◈ Tools",
                (
                    "<b>Hand Replayer</b>: replay any saved hand step by step. "
                    "<b>Equity Calculator</b>: the chances of hands or ranges on any "
                    "board. <b>My Stats</b>: your own VPIP, PFR, aggression and "
                    "results. <b>Sessions</b>: every saved game, its chip graph and "
                    "its hands; a session can be deleted there. PokerStars and "
                    "Winamax hand histories can be imported: they stay in the "
                    "list.",
                ),
            ),
        ),
    ),
    Section(
        key="table",
        title="At the table",
        intro="What you see and what you can do while playing.",
        topics=(
            Topic(
                "Acting",
                (
                    "Only the legal actions are enabled. Size a bet or raise with "
                    "the slider, the box or the presets (Min, 1/2 Pot, Pot, Max).",
                    "The <b>action clock</b> gives you a time to act, then a time "
                    "bank; when both run out you check if you can, or fold. "
                    "<b>Pause</b> stops the clock and the bots.",
                ),
            ),
            Topic(
                "Reading the table",
                (
                    "<b>Show in BB</b> shows every amount in big blinds. Once an "
                    "all-in is called, the cards are turned face up with each "
                    "player's chance of winning.",
                    "The <b>hand history</b> on the right shows every hand with its "
                    "cards and coloured actions; the <b>History</b> button hides or "
                    "shows it. <b>Replay</b> opens the last hand in a replayer "
                    "window while the table goes on.",
                ),
            ),
            Topic(
                "Several tables",
                (
                    "Every game plays in a window of its own. When a table needs "
                    "you, its window is framed in yellow and comes to the front (it "
                    "can be turned off in the settings). <b>Tile</b> (Ctrl+T) "
                    "arranges the tables side by side, <b>Cascade</b> stacks them; "
                    "the main menu lists the open tables.",
                ),
            ),
            Topic(
                "Settings and bankroll",
                (
                    "The <b>⚙</b> button (Ctrl+,) opens the settings from any "
                    "window: your name, sounds, the bots' cards at showdown, the "
                    "table speed. The bankroll screen shows your balance, a graph "
                    "and every buy-in and prize. <b>Delete all data…</b> in the "
                    "settings starts again from zero, after a confirmation.",
                ),
            ),
        ),
    ),
    Section(
        key="bots",
        title="Bot styles",
        intro=(
            "Each bot has a play style. The meters go from 1 (very little) to 5 (a "
            "lot): how many hands it plays, how often it bets and raises rather "
            "than calls, how much it bluffs, how far it calls down with a weak "
            "hand, and how strong it is overall."
        ),
    ),
    Section(
        key="terms",
        title="Poker terms",
        intro="The words of poker used in the application.",
        topics=(
            Topic(
                "Positions",
                (
                    "<b>BTN</b> the button (the dealer), the best seat: it acts last "
                    "after the flop. <b>SB</b> and <b>BB</b> the small and big "
                    "blinds, forced bets. <b>UTG</b> (under the gun) acts first "
                    "before the flop, then <b>UTG+1</b>, <b>UTG+2</b>, <b>LJ</b> "
                    "(lojack), <b>HJ</b> (hijack) and <b>CO</b> (cutoff).",
                ),
            ),
            Topic(
                "Actions",
                (
                    "<b>Check</b>: pass without betting. <b>Call</b>: match the bet. "
                    "<b>Raise</b>: bet more. <b>All-in</b>: bet every chip. A "
                    "<b>3-bet</b> is a re-raise, a <b>C-bet</b> (continuation bet) a "
                    "bet on the flop by the player who raised before it. A "
                    "<b>limp</b> is a call of the big blind instead of a raise.",
                ),
            ),
            Topic(
                "Statistics",
                (
                    "<b>VPIP</b>: share of hands a player puts money in voluntarily. "
                    "<b>PFR</b>: share of hands raised before the flop. <b>AF</b> "
                    "(aggression factor): bets and raises per call. <b>WTSD</b>: "
                    "share of hands that go to showdown. <b>bb/100</b>: big blinds "
                    "won per 100 hands. <b>ROI</b>: profit per buy-in in "
                    "tournaments.",
                ),
            ),
            Topic(
                "Strategy",
                (
                    "<b>Range</b>: all the hands a player could have, given what "
                    "they did. <b>Equity</b>: your share of the pot on average if "
                    "the cards were all dealt. <b>Pot odds</b>: what a call costs "
                    "against what it can win. <b>Expected value (EV)</b>: what an "
                    "action wins or loses on average.",
                    "<b>M ratio</b>: your stack divided by the cost of a round of "
                    "blinds and antes; below about 7, it is time to shove or fold. "
                    "<b>Push/fold</b>: going all-in or folding, nothing else. "
                    "<b>CFR</b> (counterfactual regret minimization): the method "
                    "poker AIs use to find unexploitable strategies by playing "
                    "against themselves.",
                ),
            ),
        ),
    ),
)


def section(key: str) -> Section:
    return next(s for s in SECTIONS if s.key == key)
