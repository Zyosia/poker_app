# 🎬 Demo

A tour of the **Poker** desktop app: Texas Hold'em against bots, with cash games, tournaments, Spin & Go, a Bot Arena and study tools.

Everything below was captured from the real application, playing real hands against the bots.

> 📖 Full feature list, rules and version history: [README.md](README.md) · [README.fr.md](README.fr.md)

<p align="center">
  <img src="docs/demo/cash_hand.gif" alt="Two hands played at a 6-max cash game table" width="820">
</p>

---

## Contents

- [The lobby](#the-lobby)
- [Cash games](#cash-games)
- [Multi-tabling](#multi-tabling)
- [Tournaments](#tournaments)
- [Spin & Go](#spin--go)
- [Tools](#tools)
- [Bot Arena](#bot-arena)
- [Bankroll, settings and guide](#bankroll-settings-and-guide)
- [Try it yourself](#try-it-yourself)

---

## The lobby

Pick a mode from the main menu. The tables you have open are listed at the bottom, with **Tile** and **Cascade** to arrange them. The highlighted table is the one waiting for your decision.

<p align="center">
  <img src="docs/demo/main_menu.png" alt="Main menu" width="820">
</p>

---

## Cash games

Choose how many opponents to face and each bot's play style, the betting (No Limit, Pot Limit or Fixed Limit), the stack, the blinds, a straddle, rebuys and the action clock.

<p align="center">
  <img src="docs/demo/cash_setup.png" alt="Cash game setup" width="820">
</p>

At the table you get the action clock, bet sizing buttons (Min, ½ Pot, Pot, Max) and a hand history panel. The history shows every action and showdown, with the cards.

<p align="center">
  <img src="docs/demo/cash_table.png" alt="Cash game table with the hand history" width="820">
</p>

Tables go up to **9 seats** (full ring). This one is a five-way all-in, settled with its side pots:

<p align="center">
  <img src="docs/demo/full_ring.png" alt="Full ring table, five-way all-in at showdown" width="820">
</p>

---

## Multi-tabling

Each game opens in its own window, so you can play several at once. **Tile** (`Ctrl+T`) lays them out side by side, and the table waiting for you comes to the front.

<p align="center">
  <img src="docs/demo/multi_tabling.png" alt="Four cash game tables tiled" width="900">
</p>

---

## Tournaments

Set up a tournament with any number of bots: table size, final table, blind structure, levels by hands or by time, payouts, and rebuys with an add-on.

<p align="center">
  <img src="docs/demo/tournament_setup.png" alt="Tournament setup" width="820">
</p>

Larger fields play across several tables, which are rebalanced as players bust. The **Lobby** shows the prize pool, the payouts, the blind levels, every player's stack and every table.

<table>
  <tr>
    <td width="50%"><img src="docs/demo/tournament_table.png" alt="Multi-table tournament, table 1 of 3"></td>
    <td width="50%"><img src="docs/demo/tournament_lobby.png" alt="Tournament lobby"></td>
  </tr>
  <tr>
    <td align="center"><sub>Table 1 of 3, 27 players</sub></td>
    <td align="center"><sub>The tournament lobby</sub></td>
  </tr>
</table>

---

## Spin & Go

Three-player hyper-turbos with a random prize. Pick a buy-in and the game starts straight away, or set up a custom Spin & Go.

<table>
  <tr>
    <td width="50%"><img src="docs/demo/spin_quick.png" alt="Spin & Go buy-in screen"></td>
    <td width="50%"><img src="docs/demo/spin_reveal.gif" alt="Spin & Go prize multiplier reveal"></td>
  </tr>
  <tr>
    <td align="center"><sub>Choose your buy-in</sub></td>
    <td align="center"><sub>The prize multiplier is drawn… × 10!</sub></td>
  </tr>
</table>

<p align="center">
  <img src="docs/demo/spin_table.png" alt="Spin & Go table" width="820">
</p>

---

## Tools

Every hand you play is saved, and the tools read those saved hands.

### ▶ Hand replayer

Step through any saved hand action by action, or play it back at the speed you choose. The hand below is a four-way all-in that ends in a full house.

<p align="center">
  <img src="docs/demo/hand_replayer.png" alt="Hand replayer at showdown" width="820">
</p>

### % Equity calculator

Hand against hand, or hand against a **range**. Paint the range on the 13×13 grid or start from a preset. The odds are estimated by Monte Carlo, with a margin of error.

<p align="center">
  <img src="docs/demo/equity_calculator.png" alt="Equity calculator with the range grid" width="820">
</p>

### ≡ My stats and ▤ Sessions

Your VPIP, PFR, 3-bet, aggression, WTSD, W$SD and c-bet numbers, your results by position, and a browser for every saved session with its chip graph.

<table>
  <tr>
    <td width="50%"><img src="docs/demo/my_stats.png" alt="My stats"></td>
    <td width="50%"><img src="docs/demo/session_browser.png" alt="Session browser"></td>
  </tr>
</table>

---

## Bot Arena

Seat bots of different styles together (Nit, TAG, LAG, Calling Station, Maniac, Shark, Adaptive…) and simulate thousands of hands or tournaments. The results come with confidence intervals and a chip graph, and you can export them to JSON or CSV.

<table>
  <tr>
    <td width="50%"><img src="docs/demo/bot_arena_setup.png" alt="Bot Arena setup"></td>
    <td width="50%"><img src="docs/demo/bot_arena_results.png" alt="Bot Arena results: TAG against three Maniacs over 20,000 hands"></td>
  </tr>
  <tr>
    <td align="center"><sub>Setup: TAG vs 3 Maniacs</sub></td>
    <td align="center"><sub>20,000 hands later</sub></td>
  </tr>
</table>

---

## Bankroll, settings and guide

<table>
  <tr>
    <td width="50%"><img src="docs/demo/bankroll.png" alt="Bankroll history"></td>
    <td width="50%"><img src="docs/demo/settings.png" alt="Settings"></td>
  </tr>
  <tr>
    <td align="center"><sub>Your bankroll and every buy-in, rebuy and cash-out</sub></td>
    <td align="center"><sub>Sound, table speed, four-colour deck, bots' cards…</sub></td>
  </tr>
</table>

The built-in **Guide** covers the game modes, the table, the poker vocabulary, and how each bot plays and how to beat it.

<p align="center">
  <img src="docs/demo/guide.png" alt="Guide: bot styles" width="820">
</p>

---

## Try it yourself

```bash
uv sync
uv run python -m frontend.main
```

---

<sub>This project is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE.md): free for personal, educational and other noncommercial use. Commercial use is not permitted.</sub>
