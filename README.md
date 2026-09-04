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
- [Remaining Alpha 1.x Limitations](#remaining-alpha-1x-limitations)
- [Alpha 1.2 — History and Observability](#alpha-12--history-and-observability)
- [Alpha 1.3 — Player Abstraction](#alpha-13--player-abstraction)
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

The engine separates the main responsibilities to limit coupling between system components.

```text
game/

│

├── actions.py

│   └── Player actions and bet management

│

├── betting.py

│   └── Action order and betting rounds

│

├── constants.py

│   └── Types, positions, streets, and constants

│

├── deck.py

│   └── 52-card deck

│

├── engine.py

│   └── Main session loop

│

├── hand.py

│   └── Complete hand flow

│

├── hand_evaluator.py

│   └── Hand evaluation and comparison

│

├── helper.py

│   └── Utility functions

│

├── models.py

│   └── Player, Table, Hand, and associated states

│

├── pots.py

│   └── Main pot and side pot construction

│

├── session.py

│   └── Session configuration and management

│

├── showdown.py

│   └── Winner determination and payout distribution

│

└── terminal_ui.py

    └── Terminal interface
```

The architectural principle is to separate:

```text
BETTING

"Who acts next?"

        │

        ▼

HAND EVALUATOR

"What is the value of their hand?"

        │

        ▼

SHOWDOWN

"Who wins each pot?"

        │

        ▼

POTS

"How much does each player receive?"
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

Alpha - 1.0 currently uses a **terminal** interface.

When starting a session, the engine asks for the number of players:

```text
==================================================
 TEXAS HOLD'EM — NEW SESSION
==================================================

Choose the number of players (2-6).

Number of players >
```

Players are then generated automatically:

```text
2 players

→ Player1

→ Player2
```

or:

```text
6 players

→ Player1

→ Player2

→ Player3

→ Player4

→ Player5

→ Player6
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

Current test suite status:

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

The full suite currently contains **883 passing tests**.

Goal:

> Ensure that a complete Texas Hold'em session can run without producing inconsistent game or financial state, including across repeated executions of critical scenarios.

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

The rebuy system is not yet integrated into the complete session flow.

## Cash-game Rebuy

There is not yet a mechanism allowing an eliminated player to add chips to their stack in a cash game.

## Action Abstraction for Bots

The engine currently operates through a terminal user interface.

The architecture does not yet include an abstraction allowing user input to be easily replaced by:

- an AI
- a bot
- an automated strategy
- an external API

## Complete Action History

The engine maintains the state required to play the hand, but does not yet have a complete structured history of all actions.

For example:

```text
Player1 → CALL 10

Player2 → RAISE 30

Player3 → FOLD

Player1 → CALL 20
```

is not yet stored as a usable history.

## Event Sourcing

The engine does not yet use an event-sourced architecture.

State changes are currently applied directly to the `Player`, `Hand`, and `Table` objects.

## Simulation

There is not yet a system for automatically simulating thousands or millions of hands autonomously.

The current stress tests nevertheless execute several critical scenarios 100 times to verify engine stability.

## AI

No poker AI is integrated into Alpha 1.x.

[↑ Back to table of contents](#table-of-contents)

---

# Alpha 1.2 — History and Observability

Add a proper hand history.

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

Planned features:

- [ ] `ActionEvent`
- [ ] Action history
- [ ] Street history
- [ ] Pot history
- [ ] Payout history
- [ ] Identification of the player who initiated each bet
- [ ] Structured logs

[↑ Back to table of contents](#table-of-contents)

---

# Alpha 1.3 — Player Abstraction

Fully decouple the poker engine from the terminal interface.

Create an abstraction such as:

```text
PlayerController
       │
       ├── HumanController
       │
       ├── RandomBot
       │
       ├── StrategyBot
       │
       └── AIPlayer
```

The engine could then ask:

```text
"What action should Player3 take?"
```

without knowing whether the response comes from:

- the terminal
- a bot
- an AI
- a graphical interface
- an API

[↑ Back to table of contents](#table-of-contents)

---

# Beta 1.0 — Simulation

Once player abstraction is in place, add a simulation engine.

Objectives:

- [ ] Automatically play thousands of hands
- [ ] Measure statistics
- [ ] Calculate action frequencies
- [ ] Test hand distribution
- [ ] Statistically test equity
- [ ] Test split frequency
- [ ] Test side pots
- [ ] Benchmark the engine

Example:

```text
Simulation
──────────────

Hands played : 1,000,000

Player1 wins : 24.8%

Player2 wins : 25.1%

Player3 wins : 25.0%

Player4 wins : 25.1%

Split pots : 4.7%
```

[↑ Back to table of contents](#table-of-contents)

---

# V1.0 — Advanced Poker Features

After stabilizing the V1.x engine:

- [ ] Antes
- [ ] Straddle
- [ ] Blind levels
- [ ] Tournament mode
- [ ] Cash-game mode
- [ ] Rebuy
- [ ] Add-on
- [ ] Time bank
- [ ] Configurable betting cap
- [ ] Table balancing
- [ ] Late registration
- [ ] Elimination tracking

[↑ Back to table of contents](#table-of-contents)

---

# V2.x — AI and Strategies

Once player abstraction and simulation are available:

- [ ] Basic bots
- [ ] Random bot
- [ ] Range-based bot
- [ ] Monte Carlo equity
- [ ] Pot odds
- [ ] Expected Value
- [ ] Hand range modelling
- [ ] Adaptive strategies
- [ ] Poker AI

[↑ Back to table of contents](#table-of-contents)

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

The suite now contains **883 passing tests**, covering betting rules, all-ins, re-raises, side pots, splits, showdown, eliminations, dealer rotation, chip conservation, and several complete-hand scenarios executed 100 times.

The engine core now has sufficient coverage to move to the next stage: improving the engine architecture and introducing player abstraction before implementing simulation.

Once this architecture is stabilized, advanced features can be added without compromising the engine's fundamental rules.

[↑ Back to table of contents](#table-of-contents)