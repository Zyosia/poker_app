# Poker Engine

A **Texas Hold'em No-Limit** session engine developed in Python.

The goal of this project is to progressively build a reliable and extensible poker engine capable of managing a complete multi-hand session, from card dealing to winner determination and pot distribution.

---

# Table of Contents

- [Alpha - 1.0](#alpha---10)
  - [Features](#features)

- [Hand Flow](#hand-flow)

- [Action Order](#action-order)

- [All-ins](#all-ins)

- [Hand Evaluation](#hand-evaluation)

- [Main Pots and Side Pots](#main-pots-and-side-pots)
- [Split Pots](#split-pots)

- [Chip Conservation](#chip-conservation)

- [Architecture](#architecture)

- [Session](#session)

- [Current Interface](#current-interface)

- [Alpha 1.1 — Robustness and Testing](#alpha-11--robustness-and-testing)

- [Alpha 1.2 — History and Observability](#alpha-12--history-and-observability)

- [Alpha 1.3 — Player Abstraction](#alpha-13--player-abstraction)

- [Alpha 2.0 — Desktop Application](#alpha-20--desktop-application)

- [Remaining Alpha 1.x Limitations](#remaining-alpha-1x-limitations)

- [Beta 1.0 — Simulation](#beta-10--simulation)

- [Beta 1.1 — Performance](#beta-11--performance)

- [V1.0 — Tournaments](#v10--tournaments)

- [V1.0.1 — Quality of Life](#v101--quality-of-life)

- [V1.1 — Tools](#v11--tools)

- [V1.1.1 — Tools Improvements](#v111--tools-improvements)

- [V1.2 — Settings and Sound](#v12--settings-and-sound)

- [V2.x — AI and Strategies](#v2x--ai-and-strategies)

- [V3.x — Cash Game Extras](#v3x--cash-game-extras)

- [Later / Maybe](#later--maybe)

- [Development Principles](#development-principles)

- [Project Goal](#project-goal)

---

# Alpha - 1.0

The **Alpha - 1.0** is the first functional and robust version of the poker engine core.

It covers a Texas Hold'em session with **2 to 6 players**, including betting rounds, all-ins, short all-ins, showdown, side pots, splits, and automatic chip distribution.

## Features

### 👥 Player & Table Management

| Feature | Alpha - 1.0 |
| --- | :---: |
| 2–6 players | ✅ |
| Table positions | ✅ |
| Dealer rotation | ✅ |
| Player elimination | ✅ |
| Multi-hand sessions | ✅ |

### 🃏 Hand Management

| Feature | Alpha - 1.0 |
| --- | :---: |
| Small Blind / Big Blind | ✅ |
| Hole card dealing | ✅ |
| Flop / Turn / River | ✅ |
| Community board management | ✅ |
| All-in | ✅ |
| Short all-in | ✅ |
| Auto-runout | ✅ |

### 💰 Betting System

| Feature | Alpha - 1.0 |
| --- | :---: |
| Fold | ✅ |
| Check | ✅ |
| Call | ✅ |
| Raise | ✅ |
| Re-raise | ✅ |
| Direct all-in | ✅ |
| Short all-in | ✅ |
| Minimum raise | ✅ |
| Circular action order | ✅ |
| Correct action resumption after a raise | ✅ |
| Reopening after a re-raise | ✅ |
| Tracking of the last player to act | ✅ |

The engine respects Texas Hold'em action order and does not arbitrarily restart action from the beginning of the player list after a raise.

Reopening rules are also handled when an all-in does or does not constitute a full raise.

### 🏆 Hand Evaluation

| Feature | Alpha - 1.0 |
| --- | :---: |
| Best five-card combination evaluation | ✅ |
| 9 hand categories | ✅ |
| Kicker comparison | ✅ |
| Hand comparison | ✅ |
| Tie detection | ✅ |
| Ace-low straight | ✅ |
| Ace-low straight flush | ✅ |

The hand rankings implemented in Alpha - 1.0 are:

1. High Card
2. Pair
3. Two Pair
4. Three of a Kind
5. Straight
6. Flush
7. Full House
8. Four of a Kind
9. Straight Flush

### 🏦 Pot Management

| Feature | Alpha - 1.0 |
| --- | :---: |
| Main pot | ✅ |
| Side pots | ✅ |
| Multiple side pots | ✅ |
| Contributions from folded players are accounted for | ✅ |
| Player eligibility for different pots | ✅ |
| All-in players at showdown | ✅ |
| Split pot | ✅ |
| Indivisible chip handling | ✅ |
| Automatic payout distribution | ✅ |
| Pot consistency verification | ✅ |

Each player's contribution is tracked throughout the hand so that the different pots can be reconstructed.

### 🔄 Session Flow

| Feature | Alpha - 1.0 |
| --- | :---: |
| Multiple hands in sequence | ✅ |
| Hand completion handling | ✅ |
| Automatic showdown | ✅ |
| Pot distribution | ✅ |
| Dealer rotation | ✅ |
| Automatic elimination of players without chips | ✅ |
| Session stops when only one player remains | ✅ |

[↑ Back to table of contents](#table-of-contents)

---

# Hand Flow

A hand follows the general cycle below:

```text
New hand

    │

    ├── Position assignment

    │

    ├── Small Blind / Big Blind

    │

    ├── Hole card dealing

    │

    ▼

 PREFLOP

    │

    ├── Betting round

    │

    ├── Fold?

    │     └── Yes → remaining player wins

    │

    ├── Are all players still in the hand all-in?

    │     └── Yes → Auto-runout

    │

    ▼

  FLOP

    │

    ├── Betting round

    │

    ├── Auto-runout if necessary

    │

    ▼

  TURN

    │

    ├── Betting round

    │

    ├── Auto-runout if necessary

    │

    ▼

  RIVER

    │

    ├── Betting round

    │

    ▼

 SHOWDOWN

    │

    ├── Hand Evaluation

    │

    ├── Pot construction

    │

    ├── Winner determination

    │

    ├── Split handling

    │

    └── Pot distribution

    │

    ▼

End of hand

    │

    └── Dealer rotation
```

[↑ Back to table of contents](#table-of-contents)

---

# Action Order

The engine maintains the state required to preserve a consistent circular action order.

When a player raises, action is reopened for the other players who are still able to act.

Action resumes **immediately after the raiser**, rather than from the beginning of the player list.

Example:

```text
Player1

Player2

Player3

Player2 → RAISE

Player3

   ↓

Player1
```

If Player3 then re-raises:

```text
Player2 → RAISE

    ↓

Player3 → RAISE

    ↓

Player1

    ↓

Player2
```

This mechanism handles raise and re-raise sequences without depending on the players' positions in the Python list.

The engine also tracks the last player to act, the last raiser, and the size of the last raise when required by the betting round.

[↑ Back to table of contents](#table-of-contents)

---

# All-ins

An all-in player remains **in the hand**, but can no longer act.

The engine distinguishes between:

- player still in the hand
- player able to act
- all-in player
- folded player
- eliminated player

An all-in player remains eligible for showdown and for the pots to which they contributed.

The engine also handles **short all-ins**.

A short all-in can increase the amount committed without necessarily constituting a full raise. In that case, it must not automatically reopen action for players who have already acted.

Conversely, an all-in that constitutes a full raise can reopen action.

These behaviors are covered by the engine's tests.

If all players still in the hand are all-in, no further action is requested.

The engine automatically deals the remaining board cards.

### Example

If all players are all-in preflop:

```text
PREFLOP

   ↓

ALL-IN

   ↓

FLOP

   ↓

TURN

   ↓

RIVER

   ↓

SHOWDOWN
```

If players are all-in on the flop:

```text
FLOP

   ↓

ALL-IN

   ↓

TURN

   ↓

RIVER

   ↓

SHOWDOWN
```

[↑ Back to table of contents](#table-of-contents)

---

# Hand Evaluation

The engine evaluates the best possible five-card combination from:

- the player's 2 hole cards
- the available community cards

The supported hand categories are:

1. High Card
2. Pair
3. Two Pair
4. Three of a Kind
5. Straight
6. Flush
7. Full House
8. Four of a Kind
9. Straight Flush

Ties are resolved using **tiebreakers / kickers**.

The engine also handles cases where multiple players have exactly the same best hand.

In that case, the pot is split between the relevant players.

[↑ Back to table of contents](#table-of-contents)

---

# Main Pots and Side Pots

Each player's contribution is tracked throughout the hand.

The engine can therefore reconstruct the different pots from total contributions.

### Example

```text
Player1 : 100

Player2 : 300

Player3 : 500
```

The engine builds:

```text
Main Pot

100 × 3

= 300


Side Pot #1

(300 - 100) × 2

= 400


Side Pot #2

(500 - 300) × 1

= 200
```

Each pot has its own set of eligible players.

A folded player may have contributed to a pot, but **can never win that pot**.

All-in players remain eligible for pots corresponding to their contribution level.

[↑ Back to table of contents](#table-of-contents)

---

# Split Pots

When at least two players have exactly the same hand value, the relevant pot is split between them.

Example:

```text
Pot = 200

Player1 → best hand

Player2 → best hand
```

Result:

```text
Player1 : +100

Player2 : +100
```

Any indivisible chips are awarded deterministically according to table order.

[↑ Back to table of contents](#table-of-contents)

---

# Chip Conservation

The engine verifies that chip movements remain consistent throughout a hand.

The main invariant is:

```text
Sum of player stacks

+

hand pot

=

total number of chips before the hand
```

Player contributions are included in the pot and must therefore not be counted a second time.

This property is covered by dedicated chip-conservation tests.

[↑ Back to table of contents](#table-of-contents)

---

# Architecture

The project is split into three layers with a single dependency direction:
the interface talks to the application layer, the application layer talks to
the poker engine, and the engine depends on nothing else.

```text
backend/
├── poker_engine/          Texas Hold'em rules (no UI, no bots)
│   ├── constants.py       Card, Street, ActionType and Position types
│   ├── deck.py            52-card deck
│   ├── models.py          Player, Table, Hand and history events
│   ├── actions.py         Actions and chip movements
│   ├── betting.py         Action order, legal actions, action execution
│   ├── hand.py            Hand lifecycle (start, streets, showdown)
│   ├── hand_evaluator.py  Hand evaluation and comparison
│   ├── pots.py            Main pot and side pots
│   ├── showdown.py        Winners and payouts
│   ├── history.py         Hand history recording
│   ├── blinds.py          BlindLevel (blinds, ante), BlindStructure
│   └── session.py         Session configuration, players, blind level
├── application/           Coordination between engine, controllers and UI
│   ├── controllers.py     PlayerController, HumanController, DecisionContext
│   ├── game.py            PokerGame: plays a session step by step
│   ├── setup.py           Game, tournament and Spin & Go creation
│   ├── tournament.py      Tournament, rebuys, eliminations, Spin & Go
│   ├── payouts.py         Payout structures, Spin & Go multipliers
│   ├── structures.py      Default blind structures
│   ├── hand_summary.py    A player's stats from the hand history
│   ├── action_clock.py    Action clock, time bank, clock presets (V1.0.1)
│   ├── equity.py          Run-out equity (V1.0.1), equity calculator (V1.1)
│   ├── ranges.py          Starting hands, range notation, preset ranges (V1.1.1)
│   ├── game_modes.py      Cash game, tournament, Spin & Go
│   ├── bankroll.py        Bankroll, ledger, game accounts (V1.0.1)
│   ├── profile.py         User profile file: settings and bankroll
│   ├── persistence.py     Session saving and loading (JSON, format 4)
│   ├── hand_records.py    Saved sessions read back as records (V1.1)
│   ├── replay.py          A recorded hand dealt again, step by step (V1.1)
│   └── hand_import.py     PokerStars and Winamax hand histories (V1.1.1)
├── bots/                  Computer-controlled players
│   ├── random_bot.py      Random legal actions
│   ├── basic_bot.py       Hand strength and pot odds heuristics
│   ├── profiles.py        BotProfile and the play-style presets
│   ├── short_stack.py     Stack-aware tournament play
│   ├── push_fold.py       Push/fold ranges by depth and position
│   └── factory.py         Bot creation from a name (nit, tag, lag, …)
└── simulation/            Headless bot simulations (Beta 1.0)
    ├── config.py          SimulationConfig, SeatSpec, StackPolicy, seeds
    ├── table.py           ArenaTable: bots playing hands step by step
    ├── runner.py          Batches, stack policies, workers, replay
    ├── events.py          Observer notified of every step of a hand
    ├── stats.py           Mergeable player and Engine Lab statistics
    ├── invariants.py      Chip checks run after every hand
    ├── result.py          SimulationResult, JSON and CSV export
    ├── summary.py         Plain-language reading of a result
    ├── matchup.py         Heads-up matchup matrix and parameter sweep
    ├── engine_lab.py      7-card frequencies against the theory
    ├── bench.py           Single-core benchmark (Beta 1.1)
    ├── tournament_runner.py  Tournament and Spin & Go runs (V1.0)
    ├── tournament_stats.py   Finishes, ITM and ROI statistics
    ├── my_stats.py        The human's stats from saved sessions (V1.1)
    └── cli.py             python -m backend.simulation …

frontend/
├── main.py                PySide6 application entry point
├── terminal_ui.py         Terminal front-end
├── theme.py               Colors and stylesheet
├── formatting.py          Texts for cards, amounts (chips or BB), actions
├── runout.py              Cards face up and equity after an all-in is called
├── modes.py               Modes listed by the main menu
├── sounds.py              Sound effects and the player (V1.2)
├── sound_synthesis.py     Makes the sound files (python -m frontend.sound_synthesis)
├── assets/sounds/         The sound effects (WAV)
├── ui/
│   ├── main_window.py     Navigation stack (Back works everywhere), settings
│   ├── settings_dialog.py The settings window (V1.2)
│   ├── main_menu_screen.py, bankroll_screen.py         Menu and bankroll
│   ├── cash_setup_screen.py, game_screen.py            Cash game
│   ├── tournament_setup_screen.py, tournament_screen.py,
│   │   tournament_results_screen.py         Tournament and Spin & Go
│   ├── arena_setup_screen.py, arena_progress_screen.py,
│   │   arena_results_screen.py, arena_watch_screen.py  Bot Arena
│   └── tools_screen.py, replayer_screen.py, equity_screen.py,
│       my_stats_screen.py, session_browser_screen.py   Tools (V1.1)
└── components/            Card, seat, table, action panel, line and bar charts,
                           clock choice, buy-in and bankroll line, card picker,
                           range grid, bankroll bar and settings button

tests/                     Engine, application, bots, simulation and UI tests
```

The engine is driven **one step at a time**, which lets any front-end keep
control between two steps (a graphical interface never blocks):

```python
hand = start_hand(session)  # blinds, hole cards, pre-flop round

while not hand.finished:
    if hand.current_player is None:
        advance_hand(hand)  # next street, or showdown
    else:
        apply_action(hand, action)  # validated against get_legal_actions()
```

`PokerGame` (application layer) wraps this loop: each `game.step()` asks the
controller of the player to act — a bot or the human — and executes its
decision, or deals the next street.

Inside the engine, responsibilities stay separated:

```text
BETTING          "Who acts next, and what may they do?"
   ▼
HAND EVALUATOR   "What is the value of their hand?"
   ▼
SHOWDOWN         "Who wins each pot?"
   ▼
POTS             "How much does each player receive?"
```

[↑ Back to table of contents](#table-of-contents)

---

# Session

A session can contain multiple hands.

The dealer rotates among players who still have chips.

The session continues as long as at least two players still have chips.

When a player has no chips left after a hand, they can be eliminated from the session.

The session ends when only one player with chips remains.

The dealer is determined by an index corresponding to player creation order.

For example:

```python
session = make_session(alice, bob, charlie)

session.table.dealer_index = 0
```

means that **Alice is on the button**.

The dealer then rotates clockwise, skipping players who can no longer participate in the session.

[↑ Back to table of contents](#table-of-contents)

---

# Current Interface

The application is a **PySide6 desktop application**. It opens on a **main
menu** listing the modes: **Cash Game**, **Tournament**, **Spin & Go** and
**Bot Arena**, and **Tools**. The menu and the setup screens of the paid
modes show your **bankroll** and open the **Bankroll** screen. Every screen
has a Back button, and the **⚙** button at the top left opens the
**settings** (your name, sounds, table options) from anywhere, see
[V1.2](#v12--settings-and-sound).

```bash
uv sync                        # install the dependencies
uv run python -m frontend.main # start the desktop application
```

**Cash Game** — one human player against 1 to 5 bots:

- **Setup**: number of opponents, bot level, starting stack (the buy-in,
  paid from the bankroll), blinds and action clock; you play under the name
  chosen in the settings.
- **Table**: seats, hole cards, community cards, bets, pot and dealer button;
  **Show in BB** switches every amount to big blinds. Once an all-in is
  called, the cards are turned face up with each player's chance of winning.
- **Action panel**: only the actions the engine reports as legal are enabled,
  with a slider and presets (Min, 1/2 Pot, Pot, Max) to size a bet or raise,
  and the **action clock** with its time bank; **Pause** freezes it.
- **Hand history**: every action, street and result of the session.
- **Sound effects** for the cards, the chips and every action, and the
  **bots' cards** shown at showdown, at the end of each hand or always, as
  chosen in the settings.
- **Between hands**: the next hand starts on its own after the result is
  shown (**Auto next hand**, can be switched off), or rebuy when the player
  is out of chips. A **Speed** choice (Slow, Normal, Fast, Turbo) sets how
  fast the bots act and the next hand comes. Leaving the table cashes your
  stack out to the bankroll.

See [V1.0.1](#v101--quality-of-life) for the BB display, the all-in reveal,
the action clock and the bankroll.

**Tournament** and **Spin & Go** — you against bots with rising blinds, see
[V1.0](#v10--tournaments).

**Bot Arena** — bots against bots (cash tables, tournaments and Spin & Go),
see [Beta 1.0](#beta-10--simulation) and [V1.0](#v10--tournaments).

**Tools** — the hand replayer, the equity calculator, your stats across
sessions and the session browser, see [V1.1](#v11--tools); cards picked with
the mouse, ranges, and PokerStars and Winamax hand histories, see
[V1.1.1](#v111--tools-improvements).

A minimal terminal front-end using the same application layer is also
available:

```bash
uv run python -m frontend.terminal_ui
```

[↑ Back to table of contents](#table-of-contents)

---

# Alpha 1.1 — Robustness and Testing

**Alpha 1.1** is dedicated to engine robustness and test coverage.

## Tests

The engine core currently has an automated test suite covering the main Texas Hold'em rules.

The tests cover:

```text
Hand evaluator

    ├── 9 hand categories

    ├── Kickers

    ├── Straights

    ├── Ace-low

    └── Comparison


Betting

    ├── Fold

    ├── Check

    ├── Call

    ├── Raise

    ├── Re-raise

    ├── Action order

    └── Reopening


All-ins

    ├── Full all-in

    ├── Short all-in

    ├── Minimum raise

    └── Reopening


Pots

    ├── Main pot

    ├── Side pots

    ├── Multiple side pots

    └── Eligibility


Showdown

    ├── Best hand

    ├── Fold resolution

    ├── Split pots

    └── Pot accounting


Session

    ├── Dealer rotation

    └── Eliminations


Chip integrity

    └── Chip conservation
```

Test suite status at the end of Alpha 1.1 (the current count is given in
[V1.0](#v10--tournaments)):

```text
883 passed
```

### Current Status

- [x] Complete hand evaluator tests
- [x] Side pot tests
- [x] Split pot tests
- [x] All-in tests
- [x] Action order tests
- [x] Re-raise tests
- [x] Elimination tests
- [x] Chip conservation tests
- [x] Short all-in handling
- [x] User action validation
- [x] Pot integrity verification
- [x] Correct action resumption after a raise
- [x] Dealer rotation

### Integration Tests

Integration tests now cover complete hands and sessions:

- [x] Complete hand through showdown
- [x] Hand ending by fold
- [x] Hand with all-in and auto-runout
- [x] Hand with side pot
- [x] Multiple consecutive hands
- [x] Dealer rotation between multiple hands
- [x] Chip conservation across a complete session

### Stress Tests

The main integration scenarios are also executed repeatedly to detect inconsistent states and non-deterministic behavior:

```text
Complete hand       → 100 runs
Fold hand           → 100 runs
All-in auto-runout  → 100 runs
Side pot            → 100 runs
Multiple hands      → 100 runs
Raise / re-raise    → 100 runs
```

The full suite currently passes, including the Alpha 1.2 history and persistence tests.

Goal:

> Ensure that a complete Texas Hold'em session can run without producing inconsistent game or financial state, including across repeated executions of critical scenarios.

[↑ Back to table of contents](#table-of-contents)

---

# Alpha 1.2 — History and Observability

**Alpha 1.2 is complete.**

The engine now maintains a structured history for every completed hand and persists the complete session history to a `.dat` file.

Example:

```text
Hand #42

PREFLOP

Player1 → POST SB 5

Player2 → POST BB 10

Player3 → CALL 10

Player1 → RAISE 30

Player2 → CALL 20

Player3 → FOLD

FLOP

...

SHOWDOWN

...

PAYOUT

...
```

Implemented features:

- [x] `ActionEvent`
- [x] Action history
- [x] Street history
- [x] Pot history
- [x] Payout history
- [x] Identification of the player who initiated each bet
- [x] Session history containing completed hands
- [x] Session persistence to `.dat`
- [x] Persistence tests

The saved session contains the information required to reconstruct the progression of a hand and provides the foundation for the hand replayer ([V1.1](#v11--tools)).

[↑ Back to table of contents](#table-of-contents)

# Alpha 1.3 — Player Abstraction

✅ **Complete.** The poker engine is fully decoupled from any interface.

```text
PlayerController            choose_action(DecisionContext) -> Action
       │
       ├── HumanController  the interface submits the user's decision
       │
       ├── RandomBot        random legal actions
       │
       └── BasicBot         heuristics, parameterized by a BotProfile
                            (Nit, TAG, LAG, Calling Station, Maniac, …)
```

The application asks *"What action should Player3 take?"* without knowing
whether the answer comes from the desktop interface, the terminal or a bot.
A controller only receives a `DecisionContext`: its own hole cards and the
public state of the hand (stacks, bets, board, public action history), never
the opponents' hole cards.

- [x] `PlayerController`
- [x] `HumanController`
- [x] Bot controllers (`RandomBot`, `BasicBot` and its profiles)
- [x] `DecisionContext` without hidden information

[↑ Back to table of contents](#table-of-contents)

---

# Alpha 2.0 — Desktop Application

**Alpha 2.0** turns the engine into a playable desktop application.

## What changed

- **Step-driven engine**: the engine no longer prompts a terminal. It exposes
  `start_hand`, `get_legal_actions`, `apply_action` and `advance_hand`, and can
  run a complete hand without any interface.
- **Application layer**: `PokerGame` coordinates the engine and the player
  controllers, saves the session after each hand and eliminates busted bots.
- **Bots**: `RandomBot` (random legal actions) and `BasicBot` (hand strength,
  pot odds, occasional bluffs). Bots only receive a `DecisionContext`, which
  never contains the opponents' hole cards.
- **PySide6 interface**: menu, table, action panel and hand history.
- **Project layout**: `backend/poker_engine`, `backend/application`,
  `backend/bots` and `frontend`.

## Rule corrections

- A **short all-in** above the current bet is now the amount to call. Players
  who already acted may only call or fold; players who have not acted yet, or
  who face at least a full raise in total, may still raise.
- The **minimum opening bet** is the big blind.
- A **short big blind** still requires a full big blind to call.
- A player who is **all-in from a blind** is dealt cards.
- **All-ins are recorded** in the hand history.
- A raise is not offered when **no opponent can respond**.
- Players without chips are **not dealt in** and can no longer affect a hand.

## Tooling

```bash
uv run pytest            # tests
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pyright           # static analysis
```

[↑ Back to table of contents](#table-of-contents)

---

# Remaining Alpha 1.x Limitations

Some features are intentionally excluded from this first version.

The goal is to stabilize the engine core before adding more advanced mechanics.

## Antes

✅ Classic and big-blind antes since [V1.0](#v10--tournaments).

## Straddle

Straddles are not supported.

## Betting Cap

The engine does not yet have a configurable limit on the number of raises per street.

## Tournament Blinds

✅ Blind structures with levels by hands or by time since
[V1.0](#v10--tournaments). Cash games keep fixed blinds.

## Rebuy

Partially supported. In the cash game, a busted human player is offered a
rebuy of the starting stack between hands; busted bots are eliminated. The Bot
Arena has an automatic rebuy policy. Tournaments have optional rebuys
during the first levels and an add-on ([V1.0](#v10--tournaments)).

## Cash-game Rebuy

Partially supported: a busted player can rebuy, but a player who still has
chips cannot top up their stack.

## Action Abstraction for Bots

✅ Resolved in Alpha 1.3 / 2.0: the engine is driven step by step and the
application asks a `PlayerController` (desktop interface, bot, or any future
AI or API) for each decision. See [Alpha 1.3](#alpha-13--player-abstraction).

## Complete Action History

A structured history is now available for every completed hand.

The engine records:

- every player action, including blinds
- action order and street
- player position
- bet state before and after the action
- pot state after the action
- bet initiators
- community cards for each street
- pot results and payouts
- showdown evaluations

Completed hands are stored in the session history and persisted to a session `.dat` file.

## Event Sourcing

The engine does not yet use an event-sourced architecture.

State changes are currently applied directly to the `Player`, `Hand`, and `Table` objects.

## Simulation

✅ Available since [Beta 1.0](#beta-10--simulation).

## AI

No poker AI is integrated into Alpha 1.x.

[↑ Back to table of contents](#table-of-contents)

---

# Beta 1.0 — Simulation

**Beta 1.0** adds a headless simulation engine, the **Bot Arena** and the
**main menu**.

## Features

### 🤖 Simulation engine (`backend/simulation`)

- Plays thousands to millions of hands between bots, without any interface,
  by driving the engine directly (`start_hand` / `get_legal_actions` /
  `apply_action` / `advance_hand`). Nothing is saved to disk unless asked.
- **Reproducible**: the deck and every bot draw from seeded random generators.
  The budget is split into fixed-size batches whose seed derives from
  `(seed, batch index)`, so the same configuration and seed give
  **bit-identical results whatever the number of workers**. A run without a
  seed draws one and reports it.
- **Parallel**: a `multiprocessing` pool runs the batches, with progress
  reporting and cancellation.
- **Stack policies**:
  - `reset`: everyone starts every hand with the starting stack (the default,
    and the cleanest way to compare bots);
  - `rebuy`: busted players are topped back up and rebuys are counted. Stacks
    carry over inside a batch only: every batch starts from fresh stacks, and
    the starting button rotates from one batch to the next;
  - `elimination`: the budget is a number of complete sessions, each played
    until one player has every chip. A session reaching
    `max_hands_per_session` (default 5000) ranks the survivors by stack and
    is reported as capped.
- **Invariants**: chip conservation is checked after every hand. A failure
  stops the run with the seed and the hand index, and `replay_hand()` replays
  that exact hand.
- **Duplicate mode** (reset policy only): every deal is played once per cyclic
  rotation of the seats, so every bot plays every deal from every seat.

### 📊 Statistics

Every statistic is mergeable, so the results of parallel workers combine
exactly.

- **Per player**: hands, net chips, **bb/100** with its standard deviation and
  **95% confidence interval**, **VPIP**, **PFR**, **3-bet %**, **aggression
  factor** and frequency, **WTSD**, **W$SD**, c-bet and fold to c-bet, action
  frequencies per street, results by position, rebuys and finishing positions
  (win %, average finish).
- **Chip graph**: cumulative net chips, down-sampled to at most 300 points.
- **Engine Lab**: showdown hand categories, split pots, side pots per hand,
  all-in and auto run-out frequencies, hands per second, plus a check of the
  evaluator against the theoretical 7-card category frequencies.
- **Export**: JSON (everything, including the configuration and the seed) and
  CSV (one row per player).

### 🎭 Play styles

`BasicBot` is parameterized by a `BotProfile` (hand-strength thresholds, pot
odds, bet and bluff probabilities, c-bets, sizing). The default profile is
exactly the Alpha 2.0 `BasicBot`, and the cash game "Bot level" keeps its
behaviour.

| Bot             | Style                        |
| --------------- | ---------------------------- |
| Nit             | Very tight and passive       |
| TAG             | Tight-aggressive             |
| LAG             | Loose-aggressive             |
| Calling Station | Loose-passive, rarely folds  |
| Maniac          | Very loose, very aggressive  |
| Basic           | The Alpha 2.0 heuristic bot  |
| Random          | Random legal actions         |

### 🏟️ Bot Arena

- **Setup**: 2 to 6 seats (play style and optional name), presets such as
  *TAG vs 3 Maniacs* or *Full styles table (6-max)*, hands, blinds, starting
  stack, stack policy, seed, workers and duplicate mode.
- **Fast mode**: simulates in the background with a progress bar, speed,
  time remaining and Cancel, then shows the **results**: a sortable ranking,
  the chip graph, a plain-language summary based on the confidence intervals,
  an *Advanced* tab (action frequencies, results by position, Engine Lab,
  seed and configuration), JSON / CSV export and *Run again (same seed)*.
- **Watch mode**: the same hands as a fast run of the configuration, played
  on the table at an adjustable speed (slow / normal / fast, pause, step),
  with the hand history and an optional view of every player's cards.

> 📸 *Screenshot placeholder: Bot Arena results.*

## Command line

```bash
# A table of bots: prints a summary table and exports JSON + CSV
uv run python -m backend.simulation run --seats tag,maniac,maniac,maniac --hands 100000 --seed 42

# Elimination sessions, or duplicate mode
uv run python -m backend.simulation run --seats nit,tag,lag --policy elimination --sessions 500
uv run python -m backend.simulation run --seats tag,lag --hands 100000 --duplicate

# Heads-up matchup matrix, and a parameter sweep
uv run python -m backend.simulation matchup --bots nit,tag,lag,station,maniac --hands 20000
uv run python -m backend.simulation sweep --bot tag --param bluff_probability --values 0,0.1,0.2,0.3 --field station,maniac

# Engine validation, and the list of bots
uv run python -m backend.simulation engine-lab --samples 500000
uv run python -m backend.simulation bots
```

Common options: `--hands`, `--sessions`, `--blinds 5/10`, `--stack`,
`--policy reset|rebuy|elimination`, `--seed`, `--workers`, `--batch-size`,
`--max-hands-per-session`, `--duplicate`, `--history`, `--no-invariants`,
`--output DIR` and `--no-export`. Exports go to `backend/data/simulations/`
by default (ignored by git).

## Engine change

The hand evaluator now computes the best hand of 7 cards directly instead of
comparing the 21 five-card combinations: about **12× faster**, with exactly
the same results, checked against the previous algorithm (kept as
`evaluate_best_of_combinations`). No poker rule changed.

## Objectives

- [x] Automatically play thousands of hands
- [x] Measure statistics
- [x] Calculate action frequencies
- [x] Test hand distribution
- [x] Statistically test equity (7-card category frequencies)
- [x] Test split frequency
- [x] Test side pots
- [x] Benchmark the engine

## Tests

```text
1102 passed
```

[↑ Back to table of contents](#table-of-contents)

---

# Beta 1.1 — Performance

**Beta 1.1** makes the simulator faster **without changing a single result**:
the same seed still plays exactly the same cards, actions and payouts.

## Safety net

- **Golden tests** (`tests/simulation/test_golden.py`) pin six seeded
  simulations (6 BasicBots, the 6-style table with hand histories, heads-up,
  duplicate mode, auto rebuy, elimination). Each one is fingerprinted twice:
  a hash of every hand (hole cards, board, actions, pots, payouts, stacks) and
  a hash of the exported result. They were recorded before any optimization
  and have not changed since.
- **Benchmark**: fixed seeded tables played on one core, with the default
  checks (chip invariants on, no history).

```bash
uv run python -m backend.simulation bench --hands 20000 --repeat 3
```

`--repeat` plays each table several times and keeps the fastest run, which
filters out the noise of the rest of the machine.

## Results

Hands per second on one core, best of three runs of 20,000 hands, measured
alternately on the same machine:

| Table               | Beta 1.0 | Beta 1.1 | Speed-up |
| ------------------- | -------: | -------: | -------: |
| 6 BasicBots         |    1,070 |    1,500 |    ×1.40 |
| 6-style table       |      775 |    1,190 |    ×1.54 |
| Heads-up TAG vs LAG |    3,704 |    5,084 |    ×1.37 |

## Optimizations

- **Legal actions computed once per decision**: they are cached on the hand
  (`betting.get_current_legal_actions`), keyed by every value they depend on,
  and shared by the decision context and `apply_action`.
- **Cheaper decision context**: `PlayerView` and `DecisionContext` are
  immutable named tuples, several times cheaper to build than frozen
  dataclasses (one view per seat for every decision).
- **Cheaper history**: the pot history is derived from the actions, which
  already record the pot after each one, instead of being stored twice.
- **Faster hand reading for the bots**: `evaluate_rank` returns the category
  and tiebreaker without picking the five cards, a card → rank table replaces
  per-card parsing, and the bot's strength functions (pure functions of the
  cards) are cached, since a hand is read once per decision and every player
  reads the same board.
- **Engine micro-costs**: shared constants for the fold and check actions,
  and fewer passes over the seats when looking for the next player.

## What is left

The ~2,000 hands/s target on 6 BasicBots is **not reached** (about 1,500 on
this machine). No single hot spot is left: the remaining time is spread over
the pure-Python state model itself.

- **Deck shuffling** (~6%) cannot change: the same random numbers must be
  drawn to keep every result identical.
- **Event records**: `ActionEvent` stays a frozen dataclass (~4%), because it
  is the persisted history format.
- **The rest** is the betting logic, the bots' heuristics and the statistics
  collectors, each a few percent. Going further would need a different state
  representation (for example arrays instead of player objects), which is a
  redesign of the engine rather than an optimization.

Parallel workers still scale with the number of cores.

[↑ Back to table of contents](#table-of-contents)

---

# V1.0 — Tournaments

**V1.0** adds single-table **tournaments**, **Spin & Go**, **antes**,
stack-aware bots, and tournament runs in the Bot Arena.

## Features

### ⏫ Blinds and antes (engine)

- `BlindLevel` (small blind, big blind, ante, ante type) and `BlindStructure`
  (ordered levels). Levels go up **by number of hands** (always in simulations
  and tests, fully deterministic) or **by time** when you play: the time is
  measured by the application, never by the engine, and a level only changes
  between two hands. After the last level, play stays on the last level.
- **Classic antes** (every player posts) and **big-blind antes** (the big
  blind posts one ante for the whole table).
- Antes are recorded in the hand history (`post_ante`), shown in the history
  panel and in the pot.

### 🏆 Tournaments

- 2 to 6 players, starting stack, blind structure, buy-in (fictional
  currency), payout structure, optional rebuys and add-on.
- Played **until one player holds every chip**, with finishing places,
  prizes, the hand each player was knocked out on, the number of hands and
  the level reached.
- **Payout presets**: winner takes all, 65 / 35, 50 / 30 / 20. Default:
  winner takes all with 2–3 players, 65 / 35 with 4–6. Prizes are whole
  units; rounding remainders go to the higher places.
- **Rebuys** during the first 3 levels at or below the starting stack, then
  one **add-on**; both add a buy-in to the prize pool and to what the player
  invested. Bots always rebuy when allowed and take the add-on at or below
  the starting stack.

### 🎰 Spin & Go

- 3 players, hyper-turbo structure, 500 chips (25 big
  blinds at the first level).
- A **prize multiplier** is drawn from a configurable table *before* the
  first hand, with the seeded random generator; the prize pool is that many
  buy-ins. Winner takes all, 80 / 10 / 10 from ×100.

### 🧠 Short-stack bots

In a tournament, bots measure their **effective stack in big blinds** (the
smaller of their stack and the biggest opponent stack still in the hand):

- **Push/fold** at 12 big blinds or less (13 for the LAG, 15 for the
  Maniac): open-shove or fold, call shoves, using **ranges by stack depth and
  position** (`backend/bots/push_fold.py`). Never a small raise.
- **Short stack** up to 25 big blinds: 2.2 big-blind opens, all-in
  re-raises, flat calls of a raise only with a strong hand.
- A raise committing 40% of the stack becomes an all-in.
- Each profile keeps its style by widening or narrowing the base ranges. At
  8 big blinds on the button: Nit 23%, Calling Station 31%, TAG 35%, Basic
  39%, LAG 48%, Maniac 65% of hands shoved.
- Cash games are unchanged: the Beta 1.0 golden results still hold.

The 169 starting hands are ordered by all-in equity against a random hand,
computed with the project's evaluator (Monte Carlo); the percentages are
simplified approximations of Nash push/fold charts for 6-max tables.

### 🏟️ Bot Arena: tournaments

- Run types **Tournament** and **Spin & Go** next to cash runs. The budget is
  a number of tournaments; batches hold complete tournaments, each seeded from
  `(seed, tournament index)`, with a hand cap per tournament (capped
  tournaments are ranked by stack and counted in the results).
- **Seat fairness**: in tournament *t*, the bot listed at index *i* sits in
  seat *(i + t) mod n*.
- **Stats**: win %, ITM %, average place, finishing-place distribution,
  **ROI** = (prizes − invested) / invested with its 95% confidence interval,
  average length (hands, level). For Spin & Go: the multipliers drawn, the
  ROI including them, and the **ROI without the multiplier draw** (every game
  paying its expected prize pool), which compares bots on their play only.
- Results screen: finishing-place bar chart, ROI ranking, and a summary in
  finishes and ROI. Identical results on 1 and N workers.

### 🖥️ In the app

- **Tournament setup**: your name, 1 to 5 opponents (one style for all or one
  per seat), starting stack, structure (Turbo / Regular / Deep), level speed
  (by hands or by time), buy-in, payout, rebuys and add-on.
- **Spin & Go setup**: your name, 2 opponents, buy-in, level speed and
  multiplier table; a short **multiplier reveal** shows the prize pool before
  the first hand.
- **At the table**: current level and the next one with the hands or time
  left, players left, your place, average stack in big blinds, prize pool;
  short elimination notices with place and prize; rebuy and add-on prompts;
  **Pause** freezes the level clock and the table.
- **When you bust**: your place and prize, then **Watch** (the table keeps
  playing at an adjustable speed), **Skip to results** (the rest is played
  instantly, with the same hands as watching) or **Back to menu**.
- **Results**: final standings with prizes and the hand each player went
  out on, your stats (hands, VPIP / PFR, showdowns, all-ins, biggest pot),
  **Play again** and **Back to menu**. The session file is saved with the
  tournament results.

> 📸 *Screenshot placeholder: tournament table and Spin & Go reveal.*

## Rules choices

- **Antes are dead money**: they go into the pot, but never count toward the
  amount to call or toward the size of a raise.
- **Posting order with a short stack**:
  - classic ante: **ante first, then the blind**. A player who cannot cover
    the ante posts what they have and is all-in; they are still dealt in and
    can win what every other player matched of their ante;
  - big-blind ante: **blind first, then the ante** (TDA rule). The ante goes
    into the **main pot**, which every player dealt in can win, even when the
    big blind is all-in for less or folds.
- **Dead money above every remaining player**: chips that only folded
  players put in, above the contribution of every player still in, join the
  highest pot that can still be won.
- **Simultaneous eliminations**: the player who started the hand with more
  chips finishes higher. Exactly equal stacks share the best place of their
  group and split the prizes of the places they cover; an indivisible unit
  goes to the first of them clockwise from the left of the button.
- **Moving button, no dead button**: before each hand the button moves to
  the next player with chips. When the table goes from 3 to 2 players, the
  heads-up rules apply: the button posts the small blind, acts first
  pre-flop and last after the flop.
- **Levels by time**: the clock keeps running while a player thinks or is
  idle; only the explicit Pause freezes it.

## Blind structures

Tournaments start with 1500 chips. Turbo, Regular and
Deep share their levels and differ by their pace: **Turbo** 6 hands / 3 min, **Regular** 10 hands / 6 min, **Deep** 15 hands / 10 min. A big-blind ante
equal to the big blind starts at level 4 (classic antes of a tenth of the big
blind are available with `with_classic_antes`). All structures live in
`backend/application/structures.py`.

| Level | Blinds | Ante |
| ----: | -----: | ---: |
| 1 | 10 / 20 | — |
| 2 | 15 / 30 | — |
| 3 | 25 / 50 | — |
| 4 | 50 / 100 | 100 (big blind) |
| 5 | 75 / 150 | 150 (big blind) |
| 6 | 100 / 200 | 200 (big blind) |
| 7 | 150 / 300 | 300 (big blind) |
| 8 | 200 / 400 | 400 (big blind) |
| 9 | 300 / 600 | 600 (big blind) |
| 10 | 400 / 800 | 800 (big blind) |
| 11 | 500 / 1000 | 1000 (big blind) |
| 12 | 750 / 1500 | 1500 (big blind) |
| 13 | 1000 / 2000 | 2000 (big blind) |

**Spin & Go hyper-turbo** (5 hands or
2 minutes per level, 500 chips):

| Level | Blinds | Ante |
| ----: | -----: | ---: |
| 1 | 10 / 20 | — |
| 2 | 15 / 30 | — |
| 3 | 20 / 40 | — |
| 4 | 25 / 50 | 50 (big blind) |
| 5 | 30 / 60 | 60 (big blind) |
| 6 | 40 / 80 | 80 (big blind) |
| 7 | 50 / 100 | 100 (big blind) |
| 8 | 60 / 120 | 120 (big blind) |
| 9 | 80 / 160 | 160 (big blind) |
| 10 | 100 / 200 | 200 (big blind) |
| 11 | 150 / 300 | 300 (big blind) |
| 12 | 200 / 400 | 400 (big blind) |

## Spin & Go multipliers

The default table is **fair**: the expected prize pool is exactly the three
buy-ins paid. Probabilities are exact (integer weights out of 10,000).

| Multiplier | Prize pool | Probability | Payout |
| ---: | ---: | ---: | --- |
| ×2 | 2 buy-ins | 53.00% | Winner takes all |
| ×3 | 3 buy-ins | 39.00% | Winner takes all |
| ×5 | 5 buy-ins | 6.00% | Winner takes all |
| ×10 | 10 buy-ins | 1.80% | Winner takes all |
| ×100 | 100 buy-ins | 0.19% | 80 / 10 / 10 |
| ×1000 | 1000 buy-ins | 0.01% | 80 / 10 / 10 |
| **Expected** | **3 buy-ins** | | |

The **Realistic (~7% rake)** preset is close to real sites:

| Multiplier | Prize pool | Probability | Payout |
| ---: | ---: | ---: | --- |
| ×2 | 2 buy-ins | 75.00% | Winner takes all |
| ×3 | 3 buy-ins | 17.00% | Winner takes all |
| ×5 | 5 buy-ins | 6.00% | Winner takes all |
| ×10 | 10 buy-ins | 1.80% | Winner takes all |
| ×100 | 100 buy-ins | 0.19% | 80 / 10 / 10 |
| ×1000 | 1000 buy-ins | 0.01% | 80 / 10 / 10 |
| **Expected** | **2.78 buy-ins** | | |

## Command line

```bash
# 1,000 tournaments between six styles, with rebuys and a 50/30/20 payout
uv run python -m backend.simulation tournament --seats nit,tag,lag,station,maniac,basic \
    --tournaments 1000 --structure turbo --payout 50-30-20 --rebuys

# 1,000 Spin & Go games, with the realistic multiplier table
uv run python -m backend.simulation spin --seats tag,lag,maniac --tournaments 1000 \
    --multipliers realistic
```

Options: `--seats`, `--tournaments`, `--structure turbo|regular|deep`,
`--payout wta|65-35|50-30-20`, `--rebuys`, `--multipliers fair|realistic`,
`--stack`, `--buy-in`, `--seed`, `--workers`, `--batch-size` (tournaments per
batch), `--max-hands-per-tournament`, `--no-invariants`, `--output` and
`--no-export`. A chip check runs after every hand; a failure names the
tournament and the hand to replay with `replay_tournament()`.

## Session files

Session files are now **format version 2**: the blind level of the session
and of every hand, the big-blind ante of every hand (`dead_money`), and the
tournament results. `load_session_file()` reads versions 1 and 2 (a version 1
file is upgraded in memory) and rejects unknown versions with a clear message.

## Engine changes

- Antes (`post_ante`, `Hand.dead_money`) and the blind level of a session.
- The pot builder merges chips only folded players put in, above every
  remaining player, into the highest pot still contested (with a folded
  big-blind ante, this used to raise "A pot has no eligible players").
- No other rule changed; the cash-game golden results are unchanged.

## Objectives

Engine & application:

- [x] Blind levels (by hands or by time) with configurable structures
- [x] Antes (including big-blind ante)
- [x] Elimination tracking and finishing positions
- [x] Payout structures (prize pool, places paid)
- [x] Add-on and tournament rebuy (optional per structure)

Modes:

- [x] Tournament mode (single table, 2–6 players)
- [x] Spin & Go: 3 players, hyper-turbo structure, random prize multiplier

Bots & simulation:

- [x] Short-stack play (push/fold based on stack in big blinds)
- [x] Bot Arena support for tournament structures (finish %, ROI, average place)

## Tests

```text
1309 passed
```

[↑ Back to table of contents](#table-of-contents)

---

# V1.0.1 — Quality of Life

**V1.0.1** is a small update before V1.1: amounts in **big blinds**, cards
turned **face up as soon as no more betting is possible**, an **action clock**
with a **time bank**, and a persistent **bankroll**. No poker rule changed:
the cash-game and tournament golden results, and every Bot Arena result, are
unchanged, and headless simulations never use any of it.

## Features

### 🔢 Amounts in big blinds

- A **Show in BB** checkbox on every table: cash game, tournament, Spin & Go
  and Bot Arena Watch mode. It is one setting for all of them, remembered
  between launches.
- In big blinds: stacks, bets, the pot, the "Wins …" status, the amount to
  call, the raise labels, the amount box and its presets (Min, 1/2 Pot, Pot,
  Max). One decimal at most: `42.5 BB`, `20 BB`. In a tournament, the big
  blind of the level the hand is played at (a new level shows from the next
  hand); the average stack was already in big blinds.
- **Display only**: the engine and every action stay in chips. An amount
  typed in big blinds becomes the nearest chip amount within the legal range;
  the highest value of the box is the exact all-in.
- The **hand history stays in chips**: it is the record of the hand, and a
  log never mixes two units.

### 👀 Cards face up once an all-in is called

- **When**: as soon as the betting is over for the rest of the hand, that is
  when at least two players are still in the hand and **at most one of them
  can act, with nothing to call**: everyone is all-in, or the only player
  with chips has called the last all-in. The engine knows this moment (it is
  when it starts dealing the streets without decisions): `is_betting_closed(hand)`
  says so, and the engine records the action after which it happened in
  `Hand.revealed_after_action`. The interface never re-derives the rule.
- **What you see**: the cards of every player still in the hand are turned
  face up at once ("*** Cards revealed ***" in the history), then each
  remaining street is dealt about **1 s** apart (1.25 normal steps), then the
  usual showdown and payout.
- **Win %** under each player's cards during the run-out: **exact** from the
  flop (every possible board is counted), and an **estimate "≈ 38%"** before
  the flop (about 1.7 million boards: a capped sample of about 4,000 hand
  evaluations, roughly 40 ms, so the table never stalls). The estimate uses
  an RNG of its own, seeded from the cards on the table: the game's and the
  deck's RNG are never touched. Only the cards face up are known; folded
  cards count as unknown. The code (`backend/application/equity.py`) also
  runs the V1.1 equity calculator.
- The same in **Bot Arena Watch mode** (with "Show all cards" off) and when
  **watching a tournament after you bust**.
- No information leaks: nothing is shown while any player can still act.

### ⏱️ Action clock and time bank

As on online poker sites, each of your decisions has a **time to act**, shown
as a bar that runs down (orange for the last 5 seconds). When it runs out, a
**time bank** starts automatically (blue, "Time bank 34 s"). The time bank is
shared by the whole session or tournament, is topped up slowly, and unused
time to act is not added to it.

| Preset | Time to act | Starting time bank | Top-up |
| --- | ---: | ---: | --- |
| Off | — | — | — |
| Relaxed | 30 s | 120 s | +10 s every 25 hands, max 120 s |
| Standard | 20 s | 60 s | +10 s every 25 hands, max 120 s |
| Fast | 15 s | 30 s | +5 s every 25 hands, max 60 s |
| Hyper | 10 s | 20 s | +5 s every 25 hands, max 40 s |

- **Defaults**: Cash Game → Standard, Tournament → Standard (Fast for the
  Turbo structure), Spin & Go → Fast. Each setup screen has an **Action
  clock** choice, including **Off**; your choice is remembered per mode. The
  presets live in `backend/application/action_clock.py`.
- **Time out**: when both run out, the hand is dead: you **check** if
  checking is free, and **fold** otherwise (the usual online behaviour). The
  action is recorded as timed out in the hand history
  (`Hand.timed_out_actions`) and shown as "Hero ran out of time — folds".
- **Pause** freezes the action clock and the time bank, and restarts them
  exactly where they were. It also freezes the bots, levels by time and the
  next hand; the Pause button is on every table you play at.
- Bots have no clock. Headless simulations, Bot Arena results and "Skip to
  results" never use it. Time is measured in the application layer
  (`ActionClock`, with a time source tests replace); the engine never knows
  about time.

### ⏩ Table speed and auto next hand

- **Auto next hand** (on by default): once a hand is over, its result stays
  on screen for a moment, then the next hand is dealt on its own; the **Next
  hand** button still deals at once. The table waits for you when there is a
  choice to make: a rebuy when you are out of chips, or a tournament add-on.
- **Speed**, chosen at the table: how long a bot takes to act and how long
  the result stays on screen. The default, Normal, is close to online
  clients such as PokerStars or Winamax (about a second per action, about
  three seconds between hands). The board of an all-in run-out comes a
  little slower than an action. The presets live in `frontend/pacing.py`.

| Speed | Bot action / street | Result shown before the next hand |
| --- | ---: | ---: |
| Slow | 1.5 s | 5 s |
| **Normal** (default) | 0.9 s | 3 s |
| Fast | 0.45 s | 1.5 s |
| Turbo | 0.15 s | 0.6 s |

- One setting for the cash game, tournament and Spin & Go tables (also used
  when you watch a tournament after busting), remembered between launches.
  Bot Arena Watch mode keeps its own speed choice.

### 💰 Bankroll

An offline bankroll in a **fictional currency** (there is no real money
anywhere in the application), starting at **100,000**. One unit is one chip.

| Mode | Paid from the bankroll | Credited to the bankroll |
| --- | --- | --- |
| Cash game | the starting stack, when the session starts; every rebuy | your stack when you leave the table |
| Tournament | the buy-in at the start; every rebuy and the add-on | your prize, when the tournament is over |
| Spin & Go | the buy-in at the start | your prize, when it is over (high multipliers included) |
| Bot Arena | — | — |

- **Buy-in presets**, so the stakes are comparable across modes: tournaments
  100 / 500 / 1,000 / 5,000 / 10,000, Spin & Go 100 / 500 / 1,000 / 5,000
  (default 1,000 for both); custom amounts and **0-cost freerolls** are still
  allowed. The presets live in `backend/application/setup.py`. Bot Arena and
  the command line keep their own defaults (100 and 10): their exported
  results would change otherwise, and ROI does not depend on the buy-in size.
- **Not enough money**: each setup screen shows the buy-in and your bankroll;
  a mode you cannot pay for cannot be started (Play is disabled, with a
  message). Rebuys and add-ons you cannot pay for are not offered.
- **Bankroll hint** (can be turned off on the Bankroll screen): a soft
  warning when a buy-in is a large share of the bankroll, by the usual rules
  of thumb: about **20 buy-ins** for cash games, **50** for tournaments and
  Spin & Go (`RECOMMENDED_BUY_INS`). It never blocks.
- **Reload**: below **1,000** (`RELOAD_THRESHOLD`), the main menu offers a
  reload back to 100,000.
- **Bankroll screen**: the balance, the net result overall and by mode, a
  **graph** of the bankroll over time, and the **ledger** (date and time,
  type, mode, amount, balance after, description; most recent first,
  filterable by mode). **Set bankroll…** and **Reset to 100,000** are
  recorded as **adjustments**, so the history stays honest; adjustments never
  count as results.

> 📸 *Screenshot placeholder: the all-in reveal with win %, the action clock
> in the time bank, and the Bankroll screen.*

## Leaving or closing during a game

- **Cash game**: your **stack behind** (the chips not in the pot) is saved
  at the start of each hand, after each of your actions and after each hand.
  Leaving the table or quitting the application cashes it out. If the
  application closes unexpectedly, it is cashed out at the next launch, with
  a ledger entry and a message saying so. Chips already in the pot are lost,
  as with a fold.
- **Tournament and Spin & Go**: leaving while you are still in asks for
  confirmation, then **forfeits** the tournament (the buy-in is lost, and a
  "Forfeit" entry is recorded). Once you are out, leaving plays the rest of
  the tournament instantly (the same hands as watching), so your prize is
  known and credited. Closing the application during a tournament forfeits
  it too (recorded at the next launch).
- The prize is credited when the tournament is over, not when you bust:
  bots may still rebuy and make the prize pool grow.

## User profile

The settings (BB display, clock per mode, bankroll hints) and the bankroll
(balance, ledger, the game being played) are saved in `profile.json`, in the
operating system's application data folder:

| System | Location |
| --- | --- |
| Windows | `%APPDATA%\Poker\profile.json` |
| macOS | `~/Library/Application Support/Poker/profile.json` |
| Linux | `~/.local/share/Poker/profile.json` |

The file has a `format_version`. Each save writes a temporary file, keeps the
previous version as `profile.bak`, then renames the new file into place. A
damaged file is restored from the backup; the damaged file is kept aside
(`profile.damaged_<date>.json`) and you are told at launch. The application
never crashes on a bad profile and never silently loses the balance. Tests
use a temporary folder, never your profile.

## Session files

Session files are now **format version 3**: every hand also records
`revealed_after_action` (the action after which the cards were turned face
up, null if never) and `timed_out_actions` (the actions the clock decided).
`load_session_file()` reads versions 1 to 3. These two fields join the
golden tests' `ADDED_HISTORY_FIELDS`, so the golden hashes stay exactly the
same; separate tests check that both are recorded at the right point.

## Engine changes

- `is_betting_closed(hand)` and `Hand.revealed_after_action`, set by the
  engine when the betting closes; `Hand.timed_out_actions`, filled by the
  application. Nothing else changed in the engine, and the benchmark is
  unchanged (1,623 / 1,210 / 5,120 hands per second).

## Objectives

- [x] Amounts in big blinds on every table, remembered
- [x] Cards face up once no more betting is possible, streets dealt one by one, win %
- [x] Action clock and time bank, timeouts recorded, Pause freezes them
- [x] Persistent bankroll in all three modes: view, set, reset, reload
- [x] Time bank for the human player (moved from V1.2)
- [x] Auto next hand and a table speed chosen at the table

## Tests

```text
1421 passed
```

[↑ Back to table of contents](#table-of-contents)

---

# V1.1 — Tools

**V1.1** opens the **Tools** card of the main menu: four tools to study your
games, a **hand replayer**, an **equity calculator**, **My stats** and a
**session browser**. No poker rule changed: the golden results and every Bot
Arena result are unchanged.

## Features

### ▶ Hand replayer

- **Tools → Hand Replayer** opens the **last hand of your latest session**;
  the session browser opens any other hand.
- The hand is **dealt again through the engine**: the players sit down with
  the stacks they had, the deck is stacked with the recorded cards, and every
  recorded decision is played again with `apply_action`. The table shows
  exactly what it showed during the game (your cards, the bets, the pot, the
  cards turned face up after an all-in with each player's win %, the
  showdown), and the engine checks the record: a replay that does not end
  with the recorded payouts is refused (`backend/application/replay.py`).
- **Steps**: one decision, or one street dealt, as at the table. Buttons
  **|◀ ◀ Play ▶ ▶|** (keyboard: Home, Left, Space, Right, End), the table
  speeds for Play, and **◀ Hand / Hand ▶** (Page Up / Page Down) to move
  through the session. The hand history follows the step; timeouts are
  marked "(ran out of time)".
- **Show all cards** also shows the cards nobody saw; **Show in BB** is the
  setting shared by every table.
- Hands saved **before V1.1** cannot be replayed: their hole cards were not
  recorded hand by hand (see [format 4](#saved-sessions-format-4)). Their
  history is shown as text instead.

### % Equity calculator

- 2 to 6 hands, each of two cards (`AsKd`, `A♠ K♦`, `10h 9h`) or **empty for
  a random hand**, on a board of 0 to 5 cards.
- **Exact** when every hand is known and there are at most 50,000 possible
  boards (always from the flop on: 990 boards heads-up). Otherwise **Monte
  Carlo**: 60,000 random boards, with a **95% margin of error** on each
  equity (about ±0.4%).
- For each hand: its **equity** (a tie counts as a share of the pot), its
  **win %** and its **tie %**.
- The counting runs in small steps on a timer (about 40 ms each): the screen
  stays responsive, the numbers refine as it goes, and **Stop** ends it. The
  random boards come from an RNG of their own.
- The run-out win % of V1.0.1 uses the same calculator now, with the same
  numbers to the last bit (checked on 300 random situations before and
  after the change).

| Example | Equity |
| --- | ---: |
| A♥ A♦ against K♣ K♠ on 2♣ 7♦ 9♥ (exact, 990 boards) | 91.6% / 8.4% |
| A♥ A♦ against K♣ K♠ before the flop (estimate) | about 82% / 18% |
| A♠ A♦ against a random hand (estimate) | about 85% / 15% |

### ≡ My stats

- Your stats over **every saved session**, for every mode or one of them:
  sessions, hands, and **VPIP, PFR, 3-bet, aggression factor and frequency,
  flops seen, WTSD, W$SD, c-bet and fold to c-bet**, each with what was
  counted ("22 / 107") and what it measures.
- Computed by the **Bot Arena's own collectors** (`StatsCollector`, Beta
  1.0): every saved hand is rebuilt from its record and fed to them
  (`backend/simulation/my_stats.py`), so a VPIP means the same thing in My
  stats and in the Bot Arena. A test plays seeded simulations and checks that
  the stats rebuilt from the saved hands equal the live ones, field by field.
- **Results**, kept apart by mode: cash games in chips and in **bb/100** with
  its 95% confidence interval (each hand counts in its own big blinds, so
  sessions at different stakes add up), and **by position**; tournaments and
  Spin & Go: played, won, in the money, profit and ROI, with the unfinished
  ones counted apart.
- Files saved before V1.1 count too: these stats only need the actions, the
  board and the payouts, which every format records.

### ▤ Session browser

- Every game you play is saved (`backend/data/sessions/`). The browser lists
  the sessions, most recent first, for every mode or one of them: date,
  mode, hands, result (net chips, or "2nd of 6 (+1 500)") and replayable
  hands.
- A session shows a summary, the **chip graph** (your net chips, hand after
  hand) and **every hand**: blinds, your position and cards, the board, your
  result and the pot, sortable. **Replay hand** (or a double click) opens the
  replayer on that hand.
- **Open file…** shows a session file from anywhere. A file that cannot be
  read is reported, never fatal; files are read again only when they change.

> 📸 *Screenshot placeholder: the Tools screen, the replayer during an all-in
> run-out, and the session browser.*

## Saved sessions: format 4

A bug is fixed: the `Player` objects are reused from one hand to the next,
and every save wrote all the hands again from them. So the `players` of
every hand (hole cards, stacks, positions) and its `dealer` were in fact the
latest hand's, and the cards of the earlier hands were lost.

- The engine now records each hand's own **seats** when the hand starts
  (`Hand.seats`: name, stack before the antes and blinds, position, hole
  cards), and a hand's dealer is its Button.
- Session files are **format version 4**: every hand records its `seats`,
  the session the `human` player and the `mode` (cash, tournament or spin).
  `load_session_file()` reads versions 1 to 4.
- Older files work everywhere except in the replayer: the human is the first
  seat (the application always seats the human first), the mode is guessed
  (tournament results with a multiplier: Spin & Go; results or rising
  blinds: tournament; otherwise a cash game), and each hand's dealer is read
  from its Button position.
- `seats` joins the golden tests' `ADDED_HISTORY_FIELDS`: the golden hashes
  stay exactly the same.

## Engine changes

- `SeatRecord` and `Hand.seats`, recorded by `start_hand`.
- `Deck.stacked(cards)`: a deck dealing the given cards first (replayer).
- Nothing else changed in the engine. The benchmark is unchanged within
  measurement noise: run back to back on the same machine, 1,654 / 1,217 /
  5,139 hands per second against 1,747 / 1,212 / 4,641 for V1.0.1.

## Objectives

- [x] Hand replayer (built on the Alpha 1.2 history)
- [x] Equity calculator (Monte Carlo, hands vs hands / vs random, any board)
- [x] "My stats": the human player's stats across sessions (reuses the Beta 1.0 stats collectors)
- [x] Session browser (saved sessions, results, chip graph)

## Tests

```text
1516 passed
```

[↑ Back to table of contents](#table-of-contents)

---

# V1.1.1 — Tools Improvements

**V1.1.1** improves the V1.1 tools before V1.2: in the equity calculator,
cards are **picked with the mouse** and a player can hold a **range**
(painted on a grid, typed, or taken from a preset); the session browser
**opens PokerStars and Winamax hand histories** for the replayer. No poker
rule changed: the golden results and every Bot Arena result are unchanged.

## Features

### 🖱️ Picking cards

- Every hand and the board are card places: click a place, then a card of
  the **picker** (the 52 cards, one row per suit). The next empty place is
  selected at once, so a hand takes two clicks.
- Cards already used are dimmed and cannot be picked twice; a right click
  empties a place. A hand left empty is still a random hand.

### 🎯 Ranges

- Every player is a **Hand** or a **Range**. A range is painted on the
  **13 × 13 grid** (pairs on the diagonal, suited hands above it, offsuit
  below; click a hand, or drag to paint several), typed in the usual
  notation (`QQ+, AKs, A5s-A2s, KTo+, 22-55, K9s-K6s`), or taken from a
  **preset**. The number of combinations and the share of all starting
  hands are shown (`backend/application/ranges.py`).
- **Presets**, approximations of common 100 BB 6-max cash-game charts, as a
  starting point to adjust:

| Preset | Combinations | Share |
| --- | ---: | ---: |
| UTG open | 234 | 17.6% |
| HJ open | 318 | 24.0% |
| CO open | 442 | 33.3% |
| BTN open | 658 | 49.6% |
| SB open | 542 | 40.9% |
| BB vs BTN open — call | 608 | 45.9% |
| BB vs BTN open — 3-bet | 98 | 7.4% |
| SB vs BTN open — 3-bet | 140 | 10.6% |
| BTN vs CO open — 3-bet | 90 | 6.8% |
| BTN vs CO open — call | 200 | 15.1% |
| Premium (top 3%) | 34 | 2.6% |
| Any two | 1,326 | 100% |

- **How a range counts**: every combination of a range that shares no card
  with another hand or the board counts the same, as in common equity tools.
  Card removal is exact: QQ+ against AK is about 69%, because with an AK out
  only 3 AA and 3 KK combinations are left beside the 6 QQ.
- **Exact or estimated**: every combination of the ranges is counted with
  every board when there are at most 50,000 deals (AA against KK on the
  turn: 6 × 44 = 264 deals); otherwise 60,000 random deals, with the 95%
  margin of error. A random hand is the range of any two cards, so a hand
  against a random hand on the river is now exact too.
- The win % shown at the tables after an all-in is unchanged to the last
  bit (300 situations checked before and after).

### 📥 PokerStars and Winamax hand histories

- **Sessions → Open file…** reads `.txt` hand histories of **PokerStars**
  (one or more hands per file) and **Winamax** (a whole session per file).
  The file joins the list of sessions, and its hands open in the replayer.
- **Checked by the engine** (`backend/application/hand_import.py`): every
  hand is dealt again with the players, stacks, cards and decisions of the
  history, and the forced bets, the order of action, every amount, the board
  and the winners (with the rake and the uncalled bets) must be exactly
  those of the history. A hand the engine does not play as the site did is
  left out, with the reason (in the session's summary): another game than No
  Limit Hold'em, run it twice, a dead or missed blind, a straddle, a dead
  button.
- **Unknown cards**: a history only shows your cards and those shown at
  showdown. The other players get cards nobody holds, which always stay face
  down, even with "Show all cards"; a player who mucked at showdown gets the
  weakest hand left, so the winner stays the same. No win % is shown during
  an all-in run-out with an unknown hand.
- **Amounts**: real-money amounts are counted in cents (0.25 € becomes 25;
  "Show in BB" gives the usual reading), tournament chips stay chips. The
  results are before the rake.
- **Full ring**: up to 9 players dealt in. The application's own tables stay
  2 to 6 players.
- The formats were read from published sample hands and open-source parsers,
  and are tested on handwritten histories of both sites (rake, uncalled bet,
  a player sitting out, chat lines, a muck at showdown, names with spaces, a
  7-player tournament hand with antes) and on hands played by the engine,
  written as PokerStars and Winamax write them, in chips and in cents, and
  read back identically. The sites change their formats from time to time: a
  hand that cannot be read is reported, never imported wrongly.

> 📸 *Screenshot placeholder: a hand against a range on the grid, and an
> imported PokerStars hand in the replayer.*

## Engine changes

- Positions for 7, 8 and 9 players dealt in (UTG+1, UTG+2 and LJ are added;
  `MAX_HAND_PLAYERS = 9`), for full-ring histories. Hands of 2 to 6 players,
  the order of action and every rule are unchanged.

## Objectives

- [x] Cards picked with the mouse in the equity calculator
- [x] Ranges: grid, notation and presets; hands and ranges against ranges
- [x] PokerStars and Winamax hand histories in the session browser and the replayer

## Tests

```text
1575 passed
```

[↑ Back to table of contents](#table-of-contents)

---

# V1.2 — Settings and Sound

**V1.2** adds a **settings window** reachable from every screen, **sound
effects**, the **bots' cards** on demand, and the **bankroll on the setup
screens**. No poker rule changed: the engine is untouched, and the golden
results and every Bot Arena result are unchanged.

## Features

### ⚙️ Settings

- The **⚙ button** at the top left of every screen (or **Ctrl+,**) opens the
  settings in a small window over the current screen; closing it returns to
  that screen. At a table you are playing, the game **waits** while the
  window is open (as with Pause: the action clock and the level clock stop)
  and goes on when it closes; a table you paused yourself stays paused.
- Every change applies at once and is **saved in the profile**, like the
  bankroll.

| Section | Setting |
| --- | --- |
| Player | **Your name** (1 to 12 characters), used by the Cash Game, the Tournament and the Spin & Go from your next game; the setup screens show it |
| Sound | **Sound effects** on or off, **volume** (a chip sound lets you hear it), a **sound when it is your turn** |
| Tables | **Bots' cards** (below), **table speed**, **auto next hand**, **amounts in big blinds**, **four-colour deck** (♦ blue, ♣ green, on every card), **bankroll-management hints** |

- **Restore defaults** resets every setting of the window except your name.
- Speed, Auto next hand and Show in BB stay on the tables as quick switches:
  they are the same settings, so the window and the tables always agree.

### 🃏 The bots' cards

| Choice | The bots' cards are face up |
| --- | --- |
| At showdown only (default) | at showdown, or once an all-in is called, as in a real game |
| At the end of every hand | once the hand is over, folded hands included (dimmed) |
| Always | during the whole hand, to study or tune the bots |

- **Only what you see changes.** The bots still decide from their own two
  cards and the public information (`DecisionContext`): a test plays hands
  with every card face up on the screen and checks that each bot was never
  given another player's card.
- With the last two choices, the hand history lists the cards nobody showed
  at the end of the hand ("Alex had K♠ Q♦ (folded)").
- The replayer keeps its own "Show all cards" switch.

### 🔊 Sound effects

| Moment | Sound |
| --- | --- |
| The hole cards are dealt | two cards sliding |
| Flop, turn, river | a card turned over |
| Check | two knocks on the table |
| Fold | cards pushed away |
| Call / bet or raise / all-in | chips, more of them for a raise, a pile for an all-in |
| The pot goes to the winner | chips swept across the table |
| Your turn | a soft chime (can be switched off) |
| Spin & Go draw | a tick for every value flashed, then a chime for the prize, a fanfare from × 10 up |

- The sounds are **made by the project** (`frontend/sound_synthesis.py`:
  filtered noise for the cards, short ringing tones for the chips, a damped
  low tone for the knocks, bell tones for the alerts): no recorded or
  downloaded asset. `python -m frontend.sound_synthesis` writes them again in
  `frontend/assets/sounds/` (fixed seed, same sounds every time).
- They play with Qt's `QSoundEffect` (several can overlap: a call while the
  flop is dealt). The tests never open an audio device: they check what a
  silent player was asked to play.
- Nothing plays while the rest of a tournament is played instantly (skip to
  the results).

### 💰 The bankroll on the setup screens

- The **Cash Game**, **Tournament** and **Spin & Go** setup screens show the
  bankroll at the top right, with the **Bankroll** button (and **Reload**
  when it is nearly empty), as the main menu does.
- **Back** from the Bankroll screen returns to the screen it was opened from
  (the setup screen, or the menu), with the balance up to date.

> 📸 *Screenshot placeholder: the settings window over a table, with the
> bots' cards face up and the four-colour deck.*

## New dependency

- **PySide6-Addons** (the same Qt version as PySide6-Essentials) for Qt's
  multimedia module; `uv sync` installs it.
- For a PyInstaller build, the sounds folder must be copied next to the
  code: `datas=[("frontend/assets/sounds", "frontend/assets/sounds")]` in
  the `.spec` file.

## Engine changes

- None.

## Objectives

- [x] The bankroll and its button on the Cash Game, Tournament and Spin & Go setup screens; Back returns to the screen it was opened from
- [x] The bots' cards: at showdown, at the end of the hand or always (display only, the bots see nothing more)
- [x] Sound effects: cards, chips, every action, your turn, the Spin & Go draw
- [x] A settings window from every screen, even at a table: your name, sound and volume, table options

## Tests

```text
1631 passed
```

[↑ Back to table of contents](#table-of-contents)

---

# V2.x — AI and Strategies

Already available: random bot, basic bot (hand strength + pot odds), play-style profiles (Beta 1.0).

- [ ] Monte Carlo equity inside bot decisions (reuses the V1.1 equity calculator)
- [ ] Range-based bot (preflop ranges by position)
- [ ] Hand range modelling (narrowing opponents' ranges from their actions)
- [ ] Expected value–based decisions
- [ ] Adaptive / exploitative bot (uses opponents' live stats: VPIP, AF…)
- [ ] Poker AI (e.g. CFR or self-play), evaluated in Bot Arena
- [ ] M ratio (stack / cost of an orbit) in short-stack decisions: moved from
      V1.0, the push/fold ranges by effective big blinds did not need it

---

# V3.x — Cash Game Extras

Moved from V1.2, not a priority.

- [ ] Full rebuy / top-up rules (human and bots, min/max buy-in)
- [ ] Straddle

---

# Later / Maybe

- [ ] Multi-table tournaments (table balancing, late registration)
- [ ] Configurable betting cap / Limit Hold'em
- [ ] Watch mode for Bot Arena tournament runs: moved from V1.0, a tournament
      can be watched by playing it from the main menu and busting out

---

# Development Principles

The engine should remain:

### Deterministic whenever possible

Poker rules should produce a predictable result from a given state.

### Typed

The code should maintain clean **Pylance** compatibility and use type annotations wherever they provide value.

### Modular

Betting rules, hand evaluation, pot management, and the user interface should remain independent.

### Testable

Important business rules should be testable without going through the terminal interface.

### Extensible

Future graphical interfaces, bots, simulations, and APIs should be able to use the engine without modifying its fundamental rules.

[↑ Back to table of contents](#table-of-contents)

---

# Project Goal

The **Alpha - 1.0** is the **foundation of the poker engine**.

The goal is not yet to provide a complete poker application, but to have an engine capable of correctly reproducing a standard Texas Hold'em No-Limit session:

```text
Players

   ↓

Table

   ↓

Hands

   ↓

Betting

   ↓

Community Cards

   ↓

Showdown

   ↓

Pots

   ↓

Payouts

   ↓

Updated Stacks

   ↓

Next Hand
```

The engine core now has substantial test coverage, and the main rules for betting, hand evaluation, pot management, and chip management are covered by tests.

**Alpha 1.1** continues this stabilization with integration and stress tests covering complete hands and sessions.

The suite now contains **1631 passing tests** (`uv run pytest`), covering the simulation and the Bot Arena on top of betting rules, all-ins, re-raises, side pots, splits, showdown, eliminations, dealer rotation, chip conservation, and several complete-hand scenarios executed 100 times.

The engine core now has sufficient coverage to move to the next stage: improving the engine architecture and introducing player abstraction before implementing simulation.

Once this architecture is stabilized, advanced features can be added without compromising the engine's fundamental rules.

[↑ Back to table of contents](#table-of-contents)