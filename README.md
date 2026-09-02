# Poker Engine

Moteur de session **Texas Hold'em No-Limit** développé en Python.

L'objectif de ce projet est de construire progressivement un moteur de poker fiable et extensible, capable de gérer une session complète de plusieurs mains, depuis la distribution des cartes jusqu'à la détermination du ou des gagnants et à la redistribution des pots.

---

# Alpha - 1.0

La Alpha - 1.0 constitue une première version fonctionnelle du cœur du moteur de poker.

Elle couvre le déroulement complet d'une session Texas Hold'em avec **2 à 6 joueurs**, incluant les phases de mise, les all-ins, le showdown, les side pots et la redistribution automatique des jetons.

## Fonctionnalités

### 👥 Gestion des joueurs & de la table

| Fonctionnalité | Alpha - 1.0 |
|---|:---:|
| 2–6 joueurs | ✅ |
| Positions à la table | ✅ |
| Rotation du dealer | ✅ |
| Élimination des joueurs | ✅ |
| Sessions multi-hands | ✅ |

### 🃏 Gestion des mains

| Fonctionnalité | Alpha - 1.0 |
|---|:---:|
| Small Blind / Big Blind | ✅ |
| Distribution des cartes privatives | ✅ |
| Flop / Turn / River | ✅ |
| Gestion du board communautaire | ✅ |
| All-in | ✅ |
| Auto-runout | ✅ |

### 💰 Système de mise

| Fonctionnalité | Alpha - 1.0 |
|---|:---:|
| Fold | ✅ |
| Check | ✅ |
| Call | ✅ |
| Raise | ✅ |
| Re-raise | ✅ |
| All-in directement | ✅ |
| Ordre de parole circulaire | ✅ |
| Reprise correcte de l'action après un raise | ✅ |

### 🏆 Évaluation des mains

| Fonctionnalité | Alpha - 1.0 |
|---|:---:|
| Évaluation des meilleures combinaisons de 5 cartes | ✅ |
| 9 catégories de mains | ✅ |
| Comparaison des kickers | ✅ |
| Comparaison des mains | ✅ |
| Détection des égalités | ✅ |

Les rankings de mains implémentés en Alpha - 1.0 sont :

1. High Card
2. Pair
3. Two Pair
4. Three of a Kind
5. Straight
6. Flush
7. Full House
8. Four of a Kind
9. Straight Flush

### 🏦 Gestion des pots

| Fonctionnalité | Alpha - 1.0 |
|---|:---:|
| Main pot | ✅ |
| Side pots | ✅ |
| Side pots multiples | ✅ |
| Prise en compte des contributions des joueurs ayant fold | ✅ |
| Éligibilité des joueurs aux différents pots | ✅ |
| All-in players au showdown | ✅ |
| Split pot | ✅ |
| Distribution automatique des gains | ✅ |

### 🔄 Déroulement d'une session

| Fonctionnalité | Alpha - 1.0 |
|---|:---:|
| Enchaînement automatique des hands | ✅ |
| Gestion de la fin d'une hand | ✅ |
| Showdown automatique | ✅ |
| Attribution des pots | ✅ |
| Élimination automatique des joueurs sans jetons | ✅ |
| Arrêt de la session lorsqu'il ne reste qu'un joueur | ✅ |

---

# Déroulement d'une main

Une main suit le cycle général suivant :

```text
Nouvelle main
    │
    ├── Attribution des positions
    │
    ├── Small Blind / Big Blind
    │
    ├── Distribution des cartes privées
    │
    ▼
  PREFLOP
    │
    ├── Betting round
    │
    ├── Fold ?
    │     └── Oui → joueur restant gagne
    │
    ├── Tous les joueurs encore en jeu sont all-in ?
    │     └── Oui → Auto-runout
    │
    ▼
   FLOP
    │
    ├── Betting round
    │
    ├── Auto-runout si nécessaire
    │
    ▼
   TURN
    │
    ├── Betting round
    │
    ├── Auto-runout si nécessaire
    │
    ▼
  RIVER
    │
    ├── Betting round
    │
    ▼
 SHOWDOWN
    │
    ├── Évaluation des mains
    │
    ├── Construction des pots
    │
    ├── Détermination des gagnants
    │
    ├── Gestion des splits
    │
    └── Distribution des pots
    │
    ▼
 Fin de la main
    │
    └── Rotation du dealer
```

---

# Gestion de l'ordre de parole

Le moteur conserve le dernier joueur ayant agi afin de maintenir un ordre de parole circulaire cohérent.

Lorsqu'un joueur effectue un raise, l'action est rouverte pour les autres joueurs encore capables d'agir.

L'action reprend **immédiatement après le raiser**, et non au début de la liste des joueurs.

Exemple :

```text
Player1
Player2
Player3

Player2 → RAISE

Player3
   ↓
Player1
```

Si Player3 effectue ensuite une sur-relance :

```text
Player2 → RAISE
    ↓
Player3 → RAISE
    ↓
Player1
    ↓
Player2
```

Cette mécanique permet de gérer les séquences de raises et de re-raises sans dépendre de la position des joueurs dans la liste Python.

---

# Gestion des all-ins

Un joueur all-in reste **dans la main**, mais ne peut plus effectuer d'action.

Le moteur distingue donc :

* joueur encore dans la main ;
* joueur capable d'agir ;
* joueur all-in ;
* joueur ayant fold ;
* joueur éliminé.

Si tous les joueurs encore dans la main sont all-in, aucune nouvelle action n'est demandée.

Le moteur effectue automatiquement le reste du board.

### Exemple

Si tous les joueurs sont all-in préflop :

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

Si les joueurs sont all-in au flop :

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

---

# Évaluation des mains

Le moteur évalue la meilleure combinaison possible de cinq cartes parmi :

* les 2 cartes privées du joueur ;
* les cartes communes disponibles.

Les catégories supportées sont :

1. High Card
2. Pair
3. Two Pair
4. Three of a Kind
5. Straight
6. Flush
7. Full House
8. Four of a Kind
9. Straight Flush

Les égalités sont départagées grâce aux **tiebreakers / kickers**.

Le moteur gère également les cas où plusieurs joueurs possèdent exactement la même meilleure combinaison.

Dans ce cas, le pot est partagé.

---

# Main pots et side pots

Les contributions de chaque joueur sont conservées pendant toute la main.

Le moteur peut ainsi reconstruire les différents pots à partir des contributions totales.

### Exemple

```text
Player1 : 100
Player2 : 300
Player3 : 500
```

Le moteur construit :

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

Chaque pot possède son propre ensemble de joueurs éligibles.

Un joueur ayant fold peut avoir contribué à un pot, mais **ne peut jamais gagner ce pot**.

---

# Split Pots

Lorsqu'au moins deux joueurs possèdent une main de valeur strictement identique, le pot concerné est partagé entre eux.

Exemple :

```text
Pot = 200

Player1 → meilleure main
Player2 → meilleure main
```

Résultat :

```text
Player1 : +100
Player2 : +100
```

Les éventuels jetons indivisibles sont attribués de manière déterministe selon l'ordre de la table.

---

# Architecture

Le moteur sépare les principales responsabilités afin de limiter le couplage entre les différentes parties du système.

```text
game/
│
├── actions.py
│   └── Actions des joueurs et gestion des mises
│
├── betting.py
│   └── Ordre de parole et betting rounds
│
├── constants.py
│   └── Types, positions, streets et constantes
│
├── deck.py
│   └── Deck de 52 cartes
│
├── engine.py
│   └── Boucle principale de la session
│
├── hand.py
│   └── Déroulement complet d'une main
│
├── hand_evaluator.py
│   └── Évaluation et comparaison des mains
│
├── helper.py
│   └── Fonctions utilitaires
│
├── models.py
│   └── Player, Table, Hand et états associés
│
├── pots.py
│   └── Construction du main pot et des side pots
│
├── session.py
│   └── Configuration et gestion de la session
│
├── showdown.py
│   └── Détermination des gagnants et redistribution
│
└── terminal_ui.py
    └── Interface terminal
```

Le principe architectural est notamment de séparer :

```text
BETTING
"Qui doit parler ?"
        │
        ▼
HAND EVALUATOR
"Quelle est la valeur de sa main ?"
        │
        ▼
SHOWDOWN
"Qui gagne chaque pot ?"
        │
        ▼
POTS
"Combien doit recevoir chaque joueur ?"
```

---

# Session

Une session peut contenir plusieurs mains.

Le dealer tourne entre les joueurs encore en possession de jetons.

La session continue tant qu'au moins deux joueurs disposent encore de jetons.

Lorsqu'un joueur n'a plus de jetons après une main, il est éliminé de la session.

La session se termine lorsqu'il ne reste plus qu'un joueur possédant des jetons.

---

# Interface actuelle

La Alpha - 1.0 utilise une interface **terminal**.

Au lancement d'une session, le moteur demande le nombre de joueurs :

```text
==================================================
 TEXAS HOLD'EM — NEW SESSION
==================================================
Choose the number of players (2-6).

Number of players >
```

Les joueurs sont ensuite générés automatiquement :

```text
2 joueurs
→ Player1
→ Player2
```

ou :

```text
6 joueurs
→ Player1
→ Player2
→ Player3
→ Player4
→ Player5
→ Player6
```

---

# Limites volontairement exclues de la Alpha - 1.0

Certaines fonctionnalités ne sont volontairement pas incluses dans cette première version.

L'objectif est de stabiliser le cœur du moteur avant d'ajouter des mécaniques plus avancées.

## Short all-in / incomplete raise

Les situations où un joueur fait un all-in inférieur au montant nécessaire pour constituer une raise complète et où cela modifie les règles de reopening ne sont pas encore gérées de manière complète.

La V1 conserve une règle simplifiée :

* un raise doit respecter le minimum raise ;
* un call peut provoquer un all-in ;
* un all-in constituant un raise doit respecter le minimum raise.

La gestion complète des **short all-ins et du reopening** sera ajoutée ultérieurement.

## Antes

Les antes ne sont pas encore supportées.

## Straddle

Les straddles ne sont pas supportés.

## Betting Cap

Le moteur ne possède pas encore de limite configurable sur le nombre de raises par street.

## Tournament Blinds

Les blinds restent fixes pendant toute la session.

Il n'existe pas encore de structure de tournoi avec augmentation automatique des blinds.

## Rebuy

Le système de rebuy n'est pas encore implémenté.

## Cash-game Rebuy

Il n'existe pas encore de mécanisme permettant à un joueur éliminé d'ajouter des jetons à son stack dans le cadre d'une partie cash game.

## Action abstraite pour les bots

Le moteur fonctionne actuellement avec une interface utilisateur terminal.

L'architecture n'intègre pas encore une abstraction permettant de remplacer facilement l'entrée utilisateur par :

* une IA ;
* un bot ;
* une stratégie automatique ;
* une API externe.

## Historique complet des actions

Le moteur conserve l'état nécessaire au déroulement de la main, mais ne possède pas encore un historique structuré complet de toutes les actions.

Par exemple :

```text
Player1 → CALL 10
Player2 → RAISE 30
Player3 → FOLD
Player1 → CALL 20
```

n'est pas encore enregistré comme un historique exploitable.

## Event Sourcing

Le moteur n'utilise pas encore une architecture event-sourced.

Les changements d'état sont effectués directement sur les objets `Player`, `Hand` et `Table`.

## Simulation

Il n'existe pas encore de système permettant de simuler automatiquement des milliers ou millions de mains.

## IA

Aucune intelligence artificielle de poker n'est intégrée à la Alpha - 1.0.

---

# Roadmap

## ALPHA 1.1 — Robustesse du moteur

Priorité : renforcer le cœur existant.

* [ ] Tests unitaires complets de l'évaluateur
* [ ] Tests des side pots
* [ ] Tests des splits
* [ ] Tests des all-ins
* [ ] Tests de l'ordre de parole
* [ ] Tests des re-raises
* [ ] Tests des éliminations
* [ ] Tests de conservation des jetons
* [ ] Gestion complète des short all-ins
* [ ] Validation stricte de toutes les actions utilisateur
* [ ] Vérification systématique de l'intégrité du pot

Objectif :

> Garantir qu'aucune séquence de jeu légale ne puisse produire un état financier incohérent.

---

# ALPHA 1.2 — Historique et observabilité

Ajouter un véritable historique de la main.

Exemple :

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

Fonctionnalités prévues :

* [ ] `ActionEvent`
* [ ] historique des actions
* [ ] historique des streets
* [ ] historique des pots
* [ ] historique des payouts
* [ ] identification du joueur ayant initié chaque bet
* [ ] logs structurés

---

# ALPHA - 1.3 — Abstraction des joueurs

Découpler complètement le moteur de poker de l'interface terminal.

Créer une abstraction du type :

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

Le moteur pourrait alors demander :

```text
"Quelle action doit effectuer Player3 ?"
```

sans savoir si la réponse provient :

* du terminal ;
* d'un bot ;
* d'une IA ;
* d'une interface graphique ;
* d'une API.

---

# BETA - 1.0 — Simulation

Une fois l'architecture des joueurs abstraite, ajouter un moteur de simulation.

Objectifs :

* [ ] Jouer automatiquement des milliers de mains
* [ ] Mesurer les statistiques
* [ ] Calculer les fréquences d'actions
* [ ] Tester la distribution des mains
* [ ] Tester statistiquement l'équité
* [ ] Tester la fréquence des splits
* [ ] Tester les side pots
* [ ] Benchmark du moteur

Exemple :

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

---

# V1.0 — Fonctionnalités de poker avancées

Après stabilisation du moteur V1.x :

* [ ] Antes
* [ ] Straddle
* [ ] Blind levels
* [ ] Tournament mode
* [ ] Cash-game mode
* [ ] Rebuy
* [ ] Add-on
* [ ] Time bank
* [ ] Betting cap configurable
* [ ] Table balancing
* [ ] Late registration
* [ ] Elimination tracking

---

# V2.x — IA et stratégies

Une fois l'interface joueur abstraite et la simulation disponibles :

* [ ] Bots basiques
* [ ] Bot random
* [ ] Bot basé sur des ranges
* [ ] Monte-Carlo equity
* [ ] Pot odds
* [ ] Expected Value
* [ ] Hand range modelling
* [ ] Adaptive strategies
* [ ] Poker AI

---

# Principes de développement

Le moteur doit rester :

### Déterministe lorsque possible

Les règles du poker doivent produire un résultat prévisible à partir d'un état donné.

### Typé

Le code doit conserver une compatibilité propre avec **Pylance** et utiliser les annotations de type partout où elles apportent de la valeur.

### Modulaire

Les règles de betting, l'évaluation des mains, la gestion des pots et l'interface utilisateur doivent rester indépendantes.

### Testable

Les règles métier importantes doivent pouvoir être testées sans passer par l'interface terminal.

### Extensible

Les futures interfaces graphiques, bots, simulations et API doivent pouvoir utiliser le moteur sans modifier ses règles fondamentales.

---

# Objectif du projet

La Alpha - 1.0 constitue le **socle du moteur de poker**.

L'objectif n'est pas encore de proposer une application complète de poker, mais de disposer d'un moteur capable de reproduire correctement le déroulement d'une session Texas Hold'em No-Limit classique :

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

Une fois ce cœur stabilisé et couvert par des tests, les fonctionnalités avancées pourront être ajoutées sans remettre en cause les règles fondamentales du moteur.
