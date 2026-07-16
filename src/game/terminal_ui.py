# game/terminal_ui.py

from game.helper import clear_terminal


def display_table(table, current_player=None):
    clear_terminal()

    print("=" * 50)

    print(f"STREET : {table.street}")
    print(f"POT    : {table.pot}")

    print()

    board = " ".join(table.community_cards)

    print(f"BOARD  : {board}")

    print("\nPLAYERS\n")

    for player in table.players:

        status = []

        if player.folded:
            status.append("FOLDED")

        if player.all_in:
            status.append("ALL-IN")

        status_text = " | ".join(status)

        print(
            f"{player.name:<10}"
            f"Stack:{player.stack:<6}"
            f"Bet:{player.current_bet:<6}"
            f"{status_text}"
        )

    print("\n" + "=" * 50)

    if current_player:
        print(
            f"\n{current_player.name} hand : "
            f"{current_player.hand}"
        )


def ask_player_action(player, table):

    while True:

        print("\nChoose action:")
        print("[1] Fold")
        print("[2] Check")
        print("[3] Call")
        print("[4] Raise")

        choice = input("> ")

        if choice == "1":
            return "fold", None

        elif choice == "2":
            return "check", None

        elif choice == "3":
            return "call", None

        elif choice == "4":

            amount = int(
                input("Raise amount: ")
            )

            return "raise", amount

        else:
            print("Invalid action.")