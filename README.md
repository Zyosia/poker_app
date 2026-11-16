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

- [V1.0 — Advanced Poker Features](#v10--advanced-poker-features)

- [V2.x — AI and Strategies](#v2x--ai-and-strategies)

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
│   └── session.py         Session configuration and players
├── application/           Coordination between engine, controllers and UI
│   ├── controllers.py     PlayerController, HumanController, DecisionContext
│   ├── game.py            PokerGame: plays a session step by step
│   ├── setup.py           Game creation from the user's settings
│   └── persistence.py     Session saving (JSON)
├── bots/                  Computer-controlled players
│   ├── random_bot.py      Random legal actions
│   ├── basic_bot.py       Hand strength and pot odds heuristics
│   ├── profiles.py        BotProfile and the play-style presets
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
    └── cli.py             python -m backend.simulation …

frontend/
├── main.py                PySide6 application entry point
├── terminal_ui.py         Terminal front-end
├── theme.py               Colors and stylesheet
├── formatting.py          Texts for cards, actions and results
├── modes.py               Modes listed by the main menu
├── ui/
│   ├── main_window.py     Navigation stack (Back works everywhere)
│   ├── main_menu_screen.py
│   ├── cash_setup_screen.py, game_screen.py            Cash game
│   └── arena_setup_screen.py, arena_progress_screen.py,
│       arena_results_screen.py, arena_watch_screen.py  Bot Arena
└── components/            Card, seat, table, action panel and line chart

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
menu** listing the modes: **Cash Game** and **Bot Arena** are available,
**Tournament** and **Spin & Go** are shown as coming in V1.0, and a **Tools**
slot is reserved. Every screen has a Back button.

```bash
uv sync                        # install the dependencies
uv run python -m frontend.main # start the desktop application
```

**Cash Game** — one human player against 1 to 5 bots:

- **Setup**: player name, number of opponents, bot level, starting stack and blinds.
- **Table**: seats, hole cards, community cards, bets, pot and dealer button.
- **Action panel**: only the actions the engine reports as legal are enabled,
  with a slider and presets (Min, 1/2 Pot, Pot, Max) to size a bet or raise.
- **Hand history**: every action, street and result of the session.
- **Between hands**: next hand, or rebuy when the player is out of chips.

**Bot Arena** — bots against bots, see [Beta 1.0](#beta-10--simulation).

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
[Beta 1.0](#beta-10--simulation)):

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

The saved session contains the information required to reconstruct the progression of a hand and provides the foundation for a future hand replayer.

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

Antes are not yet supported.

## Straddle

Straddles are not supported.

## Betting Cap

The engine does not yet have a configurable limit on the number of raises per street.

## Tournament Blinds

Blinds remain fixed throughout the session.

There is not yet a tournament structure with automatic blind increases.

## Rebuy

Partially supported. In the cash game, a busted human player is offered a
rebuy of the starting stack between hands; busted bots are eliminated. The Bot
Arena has an automatic rebuy policy. There are no add-ons, rebuy limits or
rebuy periods yet.

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

Engine & application:

- [ ] Blind levels (by hands or by time) with configurable structures
- [ ] Antes (including big-blind ante)
- [ ] Elimination tracking and finishing positions
- [ ] Payout structures (prize pool, places paid)
- [ ] Add-on and tournament rebuy (optional per structure)

Modes:

- [ ] Tournament mode (single table, 2–6 players)
- [ ] Spin & Go: 3 players, hyper-turbo structure, random prize multiplier

Bots & simulation:

- [ ] Short-stack play (push/fold based on stack in big blinds)
- [ ] Bot Arena support for tournament structures (finish %, ROI, average place)

---

# V1.1 — Tools

- [ ] Hand replayer (built on the Alpha 1.2 history)
- [ ] Equity calculator (Monte Carlo, hands vs hands / vs random, any board)
- [ ] "My stats": the human player's stats across sessions (reuses the Beta 1.0 stats collectors)
- [ ] Session browser (saved sessions, results, chip graph)

---

# V1.2 — Cash Game Extras

- [ ] Full rebuy / top-up rules (human and bots, min/max buy-in)
- [ ] Straddle
- [ ] Time bank for the human player

---

# V2.x — AI and Strategies

Already available: random bot, basic bot (hand strength + pot odds), play-style profiles (Beta 1.0).

- [ ] Monte Carlo equity inside bot decisions (reuses the V1.1 equity calculator)
- [ ] Range-based bot (preflop ranges by position)
- [ ] Hand range modelling (narrowing opponents' ranges from their actions)
- [ ] Expected value–based decisions
- [ ] Adaptive / exploitative bot (uses opponents' live stats: VPIP, AF…)
- [ ] Poker AI (e.g. CFR or self-play), evaluated in Bot Arena

---

# Later / Maybe

- [ ] Multi-table tournaments (table balancing, late registration)
- [ ] Configurable betting cap / Limit Hold'em

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

The suite now contains **1102 passing tests** (`uv run pytest`), covering the simulation and the Bot Arena on top of betting rules, all-ins, re-raises, side pots, splits, showdown, eliminations, dealer rotation, chip conservation, and several complete-hand scenarios executed 100 times.

The engine core now has sufficient coverage to move to the next stage: improving the engine architecture and introducing player abstraction before implementing simulation.

Once this architecture is stabilized, advanced features can be added without compromising the engine's fundamental rules.

[↑ Back to table of contents](#table-of-contents)