# Poker Engine

Moteur de session **Texas Hold'em No-Limit** développé en Python.

L'objectif de ce projet est de construire progressivement un moteur de poker fiable et extensible, capable de gérer une session complète de plusieurs mains, depuis la distribution des cartes jusqu'à la détermination du ou des gagnants et à la redistribution des pots.

---

# Sommaire

* [Alpha - 1.0](#alpha---10)

    * [Fonctionnalités](#fonctionnalités)

* [Déroulement d'une main](#déroulement-dune-main)

* [Gestion de l'ordre de parole](#gestion-de-lordre-de-parole)

* [Gestion des all-ins](#gestion-des-all-ins)

* [Évaluation des mains](#évaluation-des-mains)

* [Main pots et side pots](#main-pots-et-side-pots)

* [Split Pots](#split-pots)

* [Conservation des jetons](#conservation-des-jetons)

* [Architecture](#architecture)

* [Session](#session)

* [Interface actuelle](#interface-actuelle)

* [Alpha 1.1 — Robustesse et tests](#alpha-11--robustesse-et-tests)

* [Alpha 1.2 — Historique et observabilité](#alpha-12--historique-et-observabilité)

* [Alpha 1.3 — Abstraction des joueurs](#alpha-13--abstraction-des-joueurs)

* [Limites restantes de la Alpha - 1.x](#limites-restantes-de-la-alpha---1x)

* [Beta 1.0 — Simulation](#beta-10--simulation)

* [V1.0 — Fonctionnalités de poker avancées](#v10--fonctionnalités-de-poker-avancées)

* [V2.x — IA et stratégies](#v2x--ia-et-stratégies)

* [Principes de développement](#principes-de-développement)

* [Objectif du projet](#objectif-du-projet)

---

# Alpha - 1.0

La **Alpha - 1.0** constitue une première version fonctionnelle et robuste du cœur du moteur de poker.

Elle couvre le déroulement d'une session Texas Hold'em avec **2 à 6 joueurs**, incluant les phases de mise, les all-ins, les short all-ins, le showdown, les side pots, les splits et la redistribution automatique des jetons.

## Fonctionnalités

### 👥 Gestion des joueurs & de la table

| Fonctionnalité          | Alpha - 1.0 |

| ----------------------- | :---------: |

| 2–6 joueurs             |      ✅      |

| Positions à la table    |      ✅      |

| Rotation du dealer      |      ✅      |

| Élimination des joueurs |      ✅      |

| Sessions multi-hands    |      ✅      |

### 🃏 Gestion des mains

| Fonctionnalité                     | Alpha - 1.0 |

| ---------------------------------- | :---------: |

| Small Blind / Big Blind            |      ✅      |

| Distribution des cartes privatives |      ✅      |

| Flop / Turn / River                |      ✅      |

| Gestion du board communautaire     |      ✅      |

| All-in                             |      ✅      |

| Short all-in                       |      ✅      |

| Auto-runout                        |      ✅      |

### 💰 Système de mise

| Fonctionnalité                              | Alpha - 1.0 |

| ------------------------------------------- | :---------: |

| Fold                                        |      ✅      |

| Check                                       |      ✅      |

| Call                                        |      ✅      |

| Raise                                       |      ✅      |

| Re-raise                                    |      ✅      |

| All-in directement                          |      ✅      |

| Short all-in                                |      ✅      |

| Minimum raise                               |      ✅      |

| Ordre de parole circulaire                  |      ✅      |

| Reprise correcte de l'action après un raise |      ✅      |

| Reopening après un re-raise                 |      ✅      |

| Gestion du dernier joueur ayant agi         |      ✅      |

Le moteur respecte l'ordre de parole du Texas Hold'em et ne redémarre pas arbitrairement l'action au début de la liste des joueurs après un raise.

Les règles de reopening sont également prises en compte lorsqu'un joueur effectue un all-in constituant ou non une raise complète.

### 🏆 Évaluation des mains

| Fonctionnalité                                     | Alpha - 1.0 |

| -------------------------------------------------- | :---------: |

| Évaluation des meilleures combinaisons de 5 cartes |      ✅      |

| 9 catégories de mains                              |      ✅      |

| Comparaison des kickers                            |      ✅      |

| Comparaison des mains                              |      ✅      |

| Détection des égalités                             |      ✅      |

| Ace-low straight                                   |      ✅      |

| Ace-low straight flush                             |      ✅      |

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

| Fonctionnalité                                           | Alpha - 1.0 |

| -------------------------------------------------------- | :---------: |

| Main pot                                                 |      ✅      |

| Side pots                                                |      ✅      |

| Side pots multiples                                      |      ✅      |

| Prise en compte des contributions des joueurs ayant fold |      ✅      |

| Éligibilité des joueurs aux différents pots              |      ✅      |

| All-in players au showdown                               |      ✅      |

| Split pot                                                |      ✅      |

| Gestion des jetons indivisibles                          |      ✅      |

| Distribution automatique des gains                       |      ✅      |

| Vérification de la cohérence du pot                      |      ✅      |

Les contributions de chaque joueur sont conservées pendant toute la main afin de permettre la reconstruction des différents pots.

### 🔄 Déroulement d'une session

| Fonctionnalité                                      | Alpha - 1.0 |

| --------------------------------------------------- | :---------: |

| Enchaînement des hands                              |      ✅      |

| Gestion de la fin d'une hand                        |      ✅      |

| Showdown automatique                                |      ✅      |

| Attribution des pots                                |      ✅      |

| Rotation du dealer                                  |      ✅      |

| Élimination automatique des joueurs sans jetons     |      ✅      |

| Arrêt de la session lorsqu'il ne reste qu'un joueur |      ✅      |

[↑ Retour au sommaire](#sommaire)

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

    │     └── Oui → joueur restant gagne

    │

    ├── Tous les joueurs encore en jeu sont all-in ?

    │     └── Oui → Auto-runout

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

[↑ Retour au sommaire](#sommaire)

---

# Gestion de l'ordre de parole

Le moteur conserve l'état nécessaire pour maintenir un ordre de parole circulaire cohérent.

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

Le moteur conserve également le dernier joueur ayant agi ainsi que le dernier raiser et la taille du dernier raise lorsque ces informations sont nécessaires au déroulement du betting round.

[↑ Retour au sommaire](#sommaire)

---

# Gestion des all-ins

Un joueur all-in reste **dans la main**, mais ne peut plus effectuer d'action.

Le moteur distingue notamment :

* joueur encore dans la main ;

* joueur capable d'agir ;

* joueur all-in ;

* joueur ayant fold ;

* joueur éliminé.

Un joueur all-in reste éligible au showdown et aux pots pour lesquels il a contribué.

Le moteur gère également les **short all-ins**.

Un short all-in peut augmenter le montant engagé sans nécessairement constituer une raise complète. Dans ce cas, il ne doit pas automatiquement rouvrir l'action aux joueurs ayant déjà agi.

À l'inverse, un all-in constituant une raise complète peut rouvrir l'action.

Ces comportements sont couverts par les tests du moteur.

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

[↑ Retour au sommaire](#sommaire)

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

Dans ce cas, le pot est partagé entre les joueurs concernés.

[↑ Retour au sommaire](#sommaire)

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

Les joueurs all-in restent éligibles aux pots correspondant à leur niveau de contribution.

[↑ Retour au sommaire](#sommaire)

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

[↑ Retour au sommaire](#sommaire)

---

# Conservation des jetons

Le moteur vérifie que les mouvements de jetons restent cohérents pendant le déroulement d'une main.

L'invariant principal est :

```text

Somme des stacks des joueurs

+

pot de la hand

=

nombre total de jetons avant la hand

```

Les contributions des joueurs sont incluses dans le pot et ne doivent donc pas être comptabilisées une seconde fois.

Cette propriété est couverte par des tests dédiés de conservation des jetons.

[↑ Retour au sommaire](#sommaire)

---

# Architecture

Le moteur sépare les principales responsabilités afin de limiter le couplage entre les différentes parties du système.

```text

game/

│

├── actions.py

│   └── Actions des joueurs et gestion des mises

│

├── betting.py

│   └── Ordre de parole et betting rounds

│

├── constants.py

│   └── Types, positions, streets et constantes

│

├── deck.py

│   └── Deck de 52 cartes

│

├── engine.py

│   └── Boucle principale de la session

│

├── hand.py

│   └── Déroulement complet d'une main

│

├── hand_evaluator.py

│   └── Évaluation et comparaison des mains

│

├── helper.py

│   └── Fonctions utilitaires

│

├── history.py

│   └── Historique des actions, streets et pots

│

├── models.py

│   └── Player, Table, Hand et modèles d'historique

│

├── pots.py

│   └── Construction du main pot et des side pots

│

├── session.py

│   └── Configuration et gestion de la session

│

├── showdown.py

│   └── Détermination des gagnants et redistribution

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

[↑ Retour au sommaire](#sommaire)

---

# Session

Une session peut contenir plusieurs mains.

Le dealer tourne entre les joueurs encore en possession de jetons.

La session continue tant qu'au moins deux joueurs disposent encore de jetons.

Lorsqu'un joueur n'a plus de jetons après une main, il peut être éliminé de la session.

La session se termine lorsqu'il ne reste plus qu'un joueur possédant des jetons.

Le dealer est déterminé par un index correspondant à l'ordre de création des joueurs.

Par exemple :

```python
session = make_session(alice, bob, charlie)

session.table.dealer_index = 0
```

signifie que **Alice est au bouton**.

La rotation du dealer s'effectue ensuite dans le sens horaire en ignorant les joueurs ne pouvant plus participer à la session.

[↑ Retour au sommaire](#sommaire)

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

[↑ Retour au sommaire](#sommaire)

---

# Alpha 1.1 — Robustesse et tests

La **Alpha 1.1** est dédiée à la robustesse du moteur et à sa couverture de tests.

## Tests

Le cœur du moteur dispose actuellement d'une suite de tests automatisés couvrant les principales règles du Texas Hold'em.

Les tests couvrent notamment :

```text

Hand evaluator

    ├── 9 catégories de mains

    ├── Kickers

    ├── Straights

    ├── Ace-low

    └── Comparaison

Betting

    ├── Fold

    ├── Check

    ├── Call

    ├── Raise

    ├── Re-raise

    ├── Ordre de parole

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

    └── Conservation des jetons

```

État actuel de la suite :

```text

All tests passing

```

### État actuel

* [x] Tests unitaires complets de l'évaluateur

* [x] Tests des side pots

* [x] Tests des splits

* [x] Tests des all-ins

* [x] Tests de l'ordre de parole

* [x] Tests des re-raises

* [x] Tests des éliminations

* [x] Tests de conservation des jetons

* [x] Gestion des short all-ins

* [x] Validation des actions utilisateur

* [x] Vérification de l'intégrité du pot

* [x] Gestion correcte de la reprise de l'action après un raise

* [x] Rotation du dealer

### Prochaine étape

Ajouter des tests d'intégration couvrant des mains et des sessions complètes :

* [ ] Hand complète jusqu'au showdown

* [ ] Hand terminée par fold

* [ ] Hand avec all-in et auto-runout

* [ ] Hand avec side pot

* [ ] Plusieurs hands consécutives

* [ ] Rotation du dealer entre plusieurs hands

* [ ] Vérification de la conservation des jetons sur une session complète

Objectif :

> Garantir qu'une session complète de Texas Hold'em puisse être exécutée sans produire d'état de jeu ou financier incohérent.

[↑ Retour au sommaire](#sommaire)

---

# Alpha 1.2 — Historique et observabilité

**Alpha 1.2 est terminée.**

Le moteur conserve désormais un historique structuré de chaque main terminée et persiste l'historique complet de la session dans un fichier `.dat`.

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

Fonctionnalités implémentées :

* [x] `ActionEvent`

* [x] Historique des actions

* [x] Historique des streets

* [x] Historique des pots

* [x] Historique des payouts

* [x] Identification du joueur ayant initié chaque bet

* [x] Historique de session contenant les mains terminées

* [x] Sauvegarde de la session dans un fichier `.dat`

* [x] Tests de persistence

Les données sauvegardées contiennent les informations nécessaires pour reconstruire le déroulement d'une main et constituent la base d'un futur replayer.

[↑ Retour au sommaire](#sommaire)

# Alpha 1.3 — Abstraction des joueurs

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

[↑ Retour au sommaire](#sommaire)

---

# Limites restantes de la Alpha - 1.x

Certaines fonctionnalités restent volontairement exclues de cette première version.

L'objectif est de stabiliser le cœur du moteur avant d'ajouter des mécaniques plus avancées.

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

Le système de rebuy n'est pas encore intégré au fonctionnement complet d'une session.

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

Un historique structuré est désormais disponible pour chaque main terminée.

Le moteur conserve notamment :

* chaque action des joueurs, y compris les blinds ;

* l'ordre des actions et la street ;

* la position du joueur ;

* l'état de la mise avant et après l'action ;

* l'état du pot après l'action ;

* l'identification des joueurs ayant initié les bets ;

* les cartes communes de chaque street ;

* les résultats des pots et les payouts ;

* les évaluations du showdown.

Les mains terminées sont conservées dans l'historique de la session et persistées dans un fichier de session `.dat`.

## Event Sourcing

Le moteur n'utilise pas encore une architecture event-sourced.

Les changements d'état sont effectués directement sur les objets `Player`, `Hand` et `Table`.

## Simulation

Il n'existe pas encore de système permettant de simuler automatiquement des
milliers ou millions de mains de manière autonome.

Les tests de stress actuels exécutent cependant plusieurs scénarios critiques
100 fois afin de vérifier la stabilité du moteur.

## IA

Aucune intelligence artificielle de poker n'est intégrée à la Alpha - 1.x.

[↑ Retour au sommaire](#sommaire)

---

# Beta 1.0 — Simulation

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

[↑ Retour au sommaire](#sommaire)

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

[↑ Retour au sommaire](#sommaire)

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

[↑ Retour au sommaire](#sommaire)

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

[↑ Retour au sommaire](#sommaire)

---

# Objectif du projet

La **Alpha - 1.0** constitue le **socle du moteur de poker**.

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

Le cœur du moteur dispose désormais d'une couverture de tests importante et les principales règles de betting, d'évaluation, de pots et de gestion des jetons sont sécurisées.

La **Alpha 1.1** poursuit cette stabilisation avec des tests d'intégration couvrant le déroulement de mains et de sessions complètes.

Une fois ce cœur stabilisé et validé de bout en bout, les fonctionnalités avancées pourront être ajoutées sans remettre en cause les règles fondamentales du moteur.

[↑ Retour au sommaire](#sommaire)