# game/actions.py

def fold(player):
    player.folded = True


def check(player, table):
    if player.current_bet != table.current_bet:
        raise ValueError("Cannot check.")


def call(player, table):
    amount_to_call = (
        table.current_bet - player.current_bet
    )

    if amount_to_call <= 0:
        return

    player.stack -= amount_to_call
    player.current_bet += amount_to_call

    table.pot += amount_to_call

    if player.stack == 0:
        player.all_in = True


def raise_bet(player, table, raise_amount):
    total_bet = table.current_bet + raise_amount

    diff = total_bet - player.current_bet

    if diff > player.stack:
        raise ValueError("Not enough chips.")

    player.stack -= diff

    player.current_bet = total_bet

    table.current_bet = total_bet

    table.pot += diff

    if player.stack == 0:
        player.all_in = True