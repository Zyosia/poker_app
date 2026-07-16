# game/betting.py

from game.actions import (
    fold,
    check,
    call,
    raise_bet
)

from game.terminal_ui import (
    display_table,
    ask_player_action
)


def betting_round(table):
    active_players = [
        p for p in table.players
        if not p.folded and not p.all_in
    ]

    for player in active_players:

        display_table(table, player)

        action, amount = ask_player_action(
            player,
            table
        )

        if action == "fold":
            fold(player)

        elif action == "check":
            check(player, table)

        elif action == "call":
            call(player, table)

        elif action == "raise":
            raise_bet(
                player,
                table,
                amount
            )