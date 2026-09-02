# game/betting.py

from __future__ import annotations

from game.actions import (
    call,
    check,
    fold,
    get_call_amount,
    get_minimum_raise_to,
    raise_bet,
)
from game.constants import ActionType
from game.models import Hand, Player
from game.session import GameSession
from game.terminal_ui import (
    ask_player_action,
    display_table,
)


def betting_round(
    session: GameSession,
    hand: Hand,
) -> bool:
    """
    Run a complete betting round.

    A betting round continues until every player who can act
    has responded to the current bet.

    The action always proceeds clockwise around the table.

    A raise reopens the action for every other player who is
    still able to act. After a raise, action resumes with the
    player immediately after the raiser.

    Returns:
        True if the betting round completed normally.
        False if the hand ended because all other players folded.
    """

    if not betting_round_can_continue(hand):
        hand.current_player = None
        return True

    players = get_players_in_betting_order(
        session=session,
        hand=hand,
    )

    if not players:
        hand.current_player = None
        return True

    # Players who still need to respond to the current bet.
    pending_players: set[int] = {
        id(player)
        for player in players
        if player.can_act
    }

    # The index of the player from which we should search
    # for the next action.
    current_index = 0

    while pending_players:
        if count_remaining_players(hand) <= 1:
            return finish_by_fold(hand)

        next_player = get_next_pending_player(
            players=players,
            pending_players=pending_players,
            start_index=current_index,
        )

        if next_player is None:
            break

        player = next_player
        player_index = players.index(player)
        player_id = id(player)

        if not player.can_act:
            pending_players.discard(player_id)

            current_index = (
                player_index + 1
            ) % len(players)

            continue

        hand.current_player = player

        display_table(
            hand=hand,
            current_player=player,
        )

        allowed_actions = get_allowed_actions(
            player=player,
            hand=hand,
        )

        action, amount = ask_player_action(
            player=player,
            hand=hand,
            allowed_actions=allowed_actions,
        )

        # Store the player who just completed an action.
        hand.last_player_to_act = player

        if action == "fold":
            fold(player)

            pending_players.discard(player_id)

            # Continue clockwise from the player who folded.
            current_index = (
                player_index + 1
            ) % len(players)

        elif action == "check":
            check(
                player=player,
                hand=hand,
            )

            pending_players.discard(player_id)

            current_index = (
                player_index + 1
            ) % len(players)

        elif action == "call":
            call(
                player=player,
                hand=hand,
            )

            pending_players.discard(player_id)

            current_index = (
                player_index + 1
            ) % len(players)

        elif action == "raise":
            if amount is None:
                raise RuntimeError(
                    "Raise amount cannot be None."
                )

            raise_bet(
                player=player,
                hand=hand,
                raise_to=amount,
            )

            # A raise reopens the action.
            #
            # Every other player who can still act must
            # respond to the new bet.
            pending_players = {
                id(other_player)
                for other_player in players
                if (
                    other_player is not player
                    and other_player.can_act
                )
            }

            # CRITICAL:
            #
            # Do NOT restart from players[0].
            #
            # Action resumes with the player immediately
            # after the raiser.
            current_index = (
                player_index + 1
            ) % len(players)

        elif action == "all_in":
            if amount is None:
                raise RuntimeError(
                    "Raise amount cannot be None."
                )

            raise_bet(
                player=player,
                hand=hand,
                raise_to=amount,
            )

            # A raise reopens the action.
            #
            # Every other player who can still act must
            # respond to the new bet.
            pending_players = {
                id(other_player)
                for other_player in players
                if (
                    other_player is not player
                    and other_player.can_act
                )
            }

            # CRITICAL:
            #
            # Do NOT restart from players[0].
            #
            # Action resumes with the player immediately
            # after the raiser.
            current_index = (
                player_index + 1
            ) % len(players)


        else:
            raise RuntimeError(
                f"Unsupported action: {action}"
            )

        if count_remaining_players(hand) <= 1:
            return finish_by_fold(hand)

        if not betting_round_can_continue(hand):
            hand.current_player = None
            return True

    hand.current_player = None

    return True


def betting_round_can_continue(
    hand: Hand,
) -> bool:
    """
    Return True when at least one player still needs
    to make a meaningful betting decision.

    If all remaining players are all-in, there is no action
    to request.

    If exactly one player can act but already matches the
    current bet, there is also no reason to request another
    action because nobody can respond.
    """

    active_players = (
        hand.table.get_active_players()
    )

    players_who_can_act = [
        player
        for player in active_players
        if player.can_act
    ]

    if not players_who_can_act:
        return False

    if len(players_who_can_act) >= 2:
        return True

    player = players_who_can_act[0]

    call_amount = (
        hand.current_bet
        - player.current_bet
    )

    return call_amount > 0


def get_next_pending_player(
    players: list[Player],
    pending_players: set[int],
    start_index: int,
) -> Player | None:
    """
    Return the next pending player in clockwise table order.

    The search wraps around the table when necessary.
    """

    player_count = len(players)

    if player_count == 0:
        return None

    for offset in range(player_count):
        index = (
            start_index + offset
        ) % player_count

        player = players[index]

        if id(player) in pending_players:
            return player

    return None


def get_players_in_betting_order(
    session: GameSession,
    hand: Hand,
) -> list[Player]:
    """
    Return players in the correct betting order.

    Preflop:
        Action starts with the player immediately left
        of the Big Blind.

    Postflop:
        Action starts with the first active player left
        of the Button.

    Players who cannot currently act are excluded.
    """

    players = session.get_players_with_chips()

    if len(players) < 2:
        return []

    ordered_players = get_table_order(
        session=session,
    )

    if hand.street == "PREFLOP":
        if hand.first_to_act is None:
            raise RuntimeError(
                "first_to_act has not been assigned."
            )

        if hand.first_to_act not in ordered_players:
            raise RuntimeError(
                "first_to_act is not an active player."
            )

        start_index = ordered_players.index(
            hand.first_to_act,
        )

    else:
        dealer = session.table.dealer

        if dealer not in ordered_players:
            raise RuntimeError(
                "Dealer is not an active player."
            )

        dealer_index = ordered_players.index(
            dealer,
        )

        start_index = (
            dealer_index + 1
        ) % len(ordered_players)

    ordered = (
        ordered_players[start_index:]
        + ordered_players[:start_index]
    )

    return [
        player
        for player in ordered
        if player.can_act
    ]


def get_table_order(
    session: GameSession,
) -> list[Player]:
    """
    Return players still seated at the table in clockwise
    order starting from the dealer.

    Folded players remain in the order because they still
    occupy their position at the table for the current hand.

    All-in players also remain in the order even though
    they cannot act.

    Busted players are excluded because they are no longer
    part of the current table.
    """

    players_with_chips = (
        session.get_players_with_chips()
    )

    if not players_with_chips:
        return []

    dealer = session.table.dealer

    if dealer.is_busted:
        raise RuntimeError(
            "Dealer is busted."
        )

    dealer_index = (
        session.table.players.index(dealer)
    )

    table_order = (
        session.table.players[dealer_index:]
        + session.table.players[:dealer_index]
    )

    return [
        player
        for player in table_order
        if not player.is_busted
    ]


def get_allowed_actions(
    player: Player,
    hand: Hand,
) -> list[ActionType]:
    """
    Return the actions currently available to a player.
    """

    actions: list[ActionType] = [
        "fold",
    ]

    call_amount = get_call_amount(
        player=player,
        hand=hand,
    )

    if call_amount == 0:
        actions.append("check")
    else:
        actions.append("call")

    minimum_raise_to = get_minimum_raise_to(
        hand=hand,
    )

    maximum_raise_to = (
        player.current_bet
        + player.stack
    )

    if (
        maximum_raise_to > hand.current_bet
        and maximum_raise_to >= minimum_raise_to
    ):
        actions.append("raise")

    if call_amount < player.stack:
        actions.append("all_in")

    return actions


def count_remaining_players(
    hand: Hand,
) -> int:
    """Return the number of players still in the hand."""

    return len(
        hand.table.get_active_players()
    )


def finish_by_fold(
    hand: Hand,
) -> bool:
    """
    Finish the hand when all but one player have folded.
    """

    active_players = (
        hand.table.get_active_players()
    )

    if len(active_players) != 1:
        return False

    hand.winner_by_fold = active_players[0]
    hand.finished = True
    hand.current_player = None

    return False