# game/hand.py

from __future__ import annotations

from .actions import (
    post_big_blind,
    post_small_blind,
)
from .betting import betting_round
from .constants import Position
from .deck import Deck
from .models import Hand
from .session import GameSession
from .showdown import resolve_hand


def start_hand(
    session: GameSession,
) -> Hand:
    """
    Play one complete Texas Hold'em hand.
    """

    session.hand_number += 1

    table = session.table

    for player in session.players:
        player.reset_for_new_hand()

    hand = Hand(
        table=table,
        deck=Deck(),
    )

    assign_positions(
        session=session,
        hand=hand,
    )

    post_blinds(
        session=session,
        hand=hand,
    )

    deal_hole_cards(
        session=session,
        hand=hand,
    )

    # --------------------------------------------------
    # PREFLOP
    # --------------------------------------------------

    hand.street = "PREFLOP"

    if not play_betting_round(
        session=session,
        hand=hand,
    ):
        resolve_hand(
            hand=hand,
        )

        return hand

    if is_hand_finished(hand):
        return hand

    if should_run_out(hand):
        deal_remaining_board(
            hand=hand,
        )

        resolve_hand(
            hand=hand,
        )

        return hand

    # --------------------------------------------------
    # FLOP
    # --------------------------------------------------

    deal_flop(hand)

    hand.reset_street_betting()

    if not play_betting_round(
        session=session,
        hand=hand,
    ):
        resolve_hand(
            hand=hand,
        )

        return hand

    if is_hand_finished(hand):
        return hand

    if should_run_out(hand):
        deal_remaining_board(
            hand=hand,
        )

        resolve_hand(
            hand=hand,
        )

        return hand

    # --------------------------------------------------
    # TURN
    # --------------------------------------------------

    deal_turn(hand)

    hand.reset_street_betting()

    if not play_betting_round(
        session=session,
        hand=hand,
    ):
        resolve_hand(
            hand=hand,
        )

        return hand

    if is_hand_finished(hand):
        return hand

    if should_run_out(hand):
        deal_remaining_board(
            hand=hand,
        )

        resolve_hand(
            hand=hand,
        )

        return hand

    # --------------------------------------------------
    # RIVER
    # --------------------------------------------------

    deal_river(hand)

    hand.reset_street_betting()

    if not play_betting_round(
        session=session,
        hand=hand,
    ):
        resolve_hand(
            hand=hand,
        )

        return hand

    if is_hand_finished(hand):
        return hand

    # --------------------------------------------------
    # SHOWDOWN
    # --------------------------------------------------

    resolve_hand(
        hand=hand,
    )

    return hand


def play_betting_round(
    session: GameSession,
    hand: Hand,
) -> bool:
    """
    Run the current betting round.

    Returns False when the hand ended by fold.
    """

    return betting_round(
        session=session,
        hand=hand,
    )


def should_run_out(
    hand: Hand,
) -> bool:
    """
    Return True when no meaningful betting action remains.

    This happens when every remaining player is all-in.

    It also handles the case where only one player can act
    and that player has already matched the current bet.
    """

    active_players = hand.table.get_active_players()

    if len(active_players) <= 1:
        return False

    players_who_can_act = [player for player in active_players if player.can_act]

    if not players_who_can_act:
        return True

    if len(players_who_can_act) == 1:
        player = players_who_can_act[0]

        return player.current_bet >= hand.current_bet

    return False


def deal_remaining_board(
    hand: Hand,
) -> None:
    """Deal every community card still missing."""

    if len(hand.community_cards) < 3:
        deal_flop(hand)

    if len(hand.community_cards) < 4:
        deal_turn(hand)

    if len(hand.community_cards) < 5:
        deal_river(hand)


def assign_positions(
    session: GameSession,
    hand: Hand,
) -> None:
    """Assign positions for the current hand."""

    table = session.table

    active_players = table.get_players_with_chips()

    player_count = len(active_players)

    if player_count < 2:
        raise RuntimeError("A hand requires at least two players.")

    dealer = table.dealer

    if dealer not in active_players:
        raise RuntimeError("Dealer is not an active player.")

    dealer_index = active_players.index(
        dealer,
    )

    ordered_players = active_players[dealer_index:] + active_players[:dealer_index]

    positions_by_player_count: dict[
        int,
        list[Position],
    ] = {
        2: [
            "BTN",
            "BB",
        ],
        3: [
            "BTN",
            "SB",
            "BB",
        ],
        4: [
            "BTN",
            "SB",
            "BB",
            "CO",
        ],
        5: [
            "BTN",
            "SB",
            "BB",
            "UTG",
            "CO",
        ],
        6: [
            "BTN",
            "SB",
            "BB",
            "UTG",
            "HJ",
            "CO",
        ],
    }

    positions = positions_by_player_count.get(
        player_count,
    )

    if positions is None:
        raise RuntimeError(f"Unsupported player count: {player_count}")

    for player in active_players:
        player.position = None

    for player, position in zip(
        ordered_players,
        positions,
    ):
        player.position = position

    if player_count == 2:
        hand.first_to_act = ordered_players[0]
        return

    big_blind_index = next(
        (
            index
            for index, player in enumerate(ordered_players)
            if player.position == "BB"
        ),
        None,
    )

    if big_blind_index is None:
        raise RuntimeError("Big Blind player could not be determined.")

    first_to_act_index = (big_blind_index + 1) % player_count

    hand.first_to_act = ordered_players[first_to_act_index]


def post_blinds(
    session: GameSession,
    hand: Hand,
) -> None:
    """Post the Small Blind and Big Blind."""

    players = session.get_players_with_chips()

    if len(players) < 2:
        raise RuntimeError("At least two players are required to post blinds.")

    # --------------------------------------------------
    # Heads-up
    # --------------------------------------------------
    #
    # BTN is also the Small Blind.
    #
    if len(players) == 2:
        small_blind_player = next(
            (player for player in players if player.position == "BTN"),
            None,
        )

    else:
        small_blind_player = next(
            (player for player in players if player.position == "SB"),
            None,
        )

    big_blind_player = next(
        (player for player in players if player.position == "BB"),
        None,
    )

    if small_blind_player is None:
        raise RuntimeError("Small Blind player could not be determined.")

    if big_blind_player is None:
        raise RuntimeError("Big Blind player could not be determined.")

    post_small_blind(
        player=small_blind_player,
        hand=hand,
        amount=session.config.small_blind,
    )

    post_big_blind(
        player=big_blind_player,
        hand=hand,
        amount=session.config.big_blind,
    )


def deal_hole_cards(
    session: GameSession,
    hand: Hand,
) -> None:
    """Deal two private cards to every player."""

    if hand.deck is None:
        raise RuntimeError("Hand deck has not been initialized.")

    players = session.get_players_with_chips()

    for _ in range(2):
        for player in players:
            player.hand.append(
                hand.deck.draw(),
            )


def deal_flop(
    hand: Hand,
) -> None:
    """Burn one card and deal the flop."""

    if hand.deck is None:
        raise RuntimeError("Hand deck has not been initialized.")

    hand.deck.burn()

    for _ in range(3):
        hand.community_cards.append(
            hand.deck.draw(),
        )

    hand.street = "FLOP"


def deal_turn(
    hand: Hand,
) -> None:
    """Burn one card and deal the turn."""

    if hand.deck is None:
        raise RuntimeError("Hand deck has not been initialized.")

    hand.deck.burn()

    hand.community_cards.append(
        hand.deck.draw(),
    )

    hand.street = "TURN"


def deal_river(
    hand: Hand,
) -> None:
    """Burn one card and deal the river."""

    if hand.deck is None:
        raise RuntimeError("Hand deck has not been initialized.")

    hand.deck.burn()

    hand.community_cards.append(
        hand.deck.draw(),
    )

    hand.street = "RIVER"


def is_hand_finished(
    hand: Hand,
) -> bool:
    """
    Return True when the hand has ended because only one
    player remains.
    """

    active_players = hand.table.get_active_players()

    if len(active_players) <= 1:
        if active_players:
            hand.winner_by_fold = active_players[0]

        hand.finished = True
        return True

    return False
