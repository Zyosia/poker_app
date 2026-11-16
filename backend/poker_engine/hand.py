"""Lifecycle of a Texas Hold'em hand.

A hand is driven step by step, so the caller (application, tests, UI) keeps
control between two steps:

1. ``start_hand`` posts the blinds, deals the hole cards and opens the
   pre-flop betting round.
2. While ``hand.current_player`` is set, that player's decision is executed
   with ``betting.apply_action``.
3. When the betting round is over (``hand.current_player`` is ``None``),
   ``advance_hand`` deals the next street or resolves the showdown.
"""

from collections.abc import Callable

from .actions import Action, post_big_blind, post_small_blind
from .betting import apply_action, begin_betting_round
from .constants import Position, Street
from .deck import Deck
from .history import record_action, record_street
from .models import Hand, Player
from .session import GameSession
from .showdown import resolve_hand

POSITIONS_BY_PLAYER_COUNT: dict[int, tuple[Position, ...]] = {
    2: (Position.BTN, Position.BB),
    3: (Position.BTN, Position.SB, Position.BB),
    4: (Position.BTN, Position.SB, Position.BB, Position.CO),
    5: (Position.BTN, Position.SB, Position.BB, Position.UTG, Position.CO),
    6: (
        Position.BTN,
        Position.SB,
        Position.BB,
        Position.UTG,
        Position.HJ,
        Position.CO,
    ),
}

ActionChooser = Callable[[Hand, Player], Action]


def start_hand(session: GameSession, deck: Deck | None = None) -> Hand:
    """Start a new hand and open the pre-flop betting round."""
    session.hand_number += 1

    for player in session.players:
        player.reset_for_new_hand()

    hand = Hand(
        table=session.table,
        deck=deck or Deck(),
        min_bet=session.config.big_blind,
    )
    session.hands.append(hand)

    assign_positions(session=session, hand=hand)
    post_blinds(session=session, hand=hand)
    deal_hole_cards(session=session, hand=hand)

    record_street(hand)
    begin_betting_round(hand)

    return hand


def advance_hand(hand: Hand) -> None:
    """Move a hand forward once its betting round is complete.

    Deals the next street and opens its betting round, or resolves the
    showdown after the river. When no betting is possible anymore (players
    all-in), each call deals one more street until the showdown.
    """
    if hand.finished:
        raise RuntimeError("The hand is already finished.")

    if hand.current_player is not None:
        raise RuntimeError("The betting round is still in progress.")

    if hand.street == Street.RIVER:
        resolve_hand(hand)
        return

    if hand.street == Street.PREFLOP:
        deal_flop(hand)
    elif hand.street == Street.FLOP:
        deal_turn(hand)
    else:
        deal_river(hand)

    record_street(hand)
    hand.reset_street_betting()
    begin_betting_round(hand)


def play_hand(
    session: GameSession,
    choose_action: ActionChooser,
    deck: Deck | None = None,
) -> Hand:
    """Play one complete hand, asking ``choose_action`` for every decision."""
    hand = start_hand(session=session, deck=deck)

    while not hand.finished:
        if hand.current_player is None:
            advance_hand(hand)
        else:
            apply_action(hand, choose_action(hand, hand.current_player))

    return hand


def assign_positions(session: GameSession, hand: Hand) -> None:
    """Assign positions for the current hand and the first pre-flop actor."""
    table = session.table
    players = table.get_players_with_chips()
    positions = POSITIONS_BY_PLAYER_COUNT.get(len(players))

    if len(players) < 2:
        raise RuntimeError("A hand requires at least two players.")

    if positions is None:
        raise RuntimeError(f"Unsupported player count: {len(players)}")

    if table.dealer not in players:
        raise RuntimeError("Dealer is not an active player.")

    dealer_index = players.index(table.dealer)
    ordered_players = players[dealer_index:] + players[:dealer_index]

    for player, position in zip(ordered_players, positions, strict=True):
        player.position = position

    # Heads-up, the Button posts the small blind and acts first pre-flop.
    # Otherwise the action starts left of the Big Blind (seat 2 from the Button).
    first_to_act_index = 0 if len(players) == 2 else 3 % len(players)
    hand.first_to_act = ordered_players[first_to_act_index]


def post_blinds(session: GameSession, hand: Hand) -> None:
    """Post the Small Blind and Big Blind."""
    players = session.get_players_with_chips()

    if len(players) < 2:
        raise RuntimeError("At least two players are required to post blinds.")

    small_blind_position = Position.BTN if len(players) == 2 else Position.SB

    small_blind_player = _find_player_at(players, small_blind_position)
    big_blind_player = _find_player_at(players, Position.BB)

    small_blind_amount = post_small_blind(
        player=small_blind_player,
        hand=hand,
        amount=session.config.small_blind,
    )
    record_action(
        hand=hand,
        player=small_blind_player,
        action="post_sb",
        amount=small_blind_amount,
        bet_before=0,
    )

    big_blind_amount = post_big_blind(
        player=big_blind_player,
        hand=hand,
        amount=session.config.big_blind,
    )
    record_action(
        hand=hand,
        player=big_blind_player,
        action="post_bb",
        amount=big_blind_amount,
        bet_before=0,
        bet_initiator=True,
    )


def deal_hole_cards(session: GameSession, hand: Hand) -> None:
    """Deal two private cards to every player, starting left of the dealer."""
    players = [
        player
        for player in session.table.players_after(session.table.dealer)
        if player.is_active and not player.is_eliminated
    ]

    for _ in range(2):
        for player in players:
            player.hand.append(hand.deck.draw())


def deal_flop(hand: Hand) -> None:
    """Burn one card and deal the flop."""
    _deal_community_cards(hand=hand, count=3, street=Street.FLOP)


def deal_turn(hand: Hand) -> None:
    """Burn one card and deal the turn."""
    _deal_community_cards(hand=hand, count=1, street=Street.TURN)


def deal_river(hand: Hand) -> None:
    """Burn one card and deal the river."""
    _deal_community_cards(hand=hand, count=1, street=Street.RIVER)


def _deal_community_cards(hand: Hand, count: int, street: Street) -> None:
    hand.deck.burn()

    for _ in range(count):
        hand.community_cards.append(hand.deck.draw())

    hand.street = street


def _find_player_at(players: list[Player], position: Position) -> Player:
    for player in players:
        if player.position == position:
            return player

    raise RuntimeError(f"{position} player could not be determined.")
