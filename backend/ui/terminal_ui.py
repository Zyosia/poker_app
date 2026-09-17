# backend/game/terminal_ui.py

from __future__ import annotations

from ..game.constants import ActionType
from ..game.helper import clear_terminal
from ..game.models.models import Hand, Player


def display_table(
    hand: Hand,
    current_player: Player | None = None,
) -> None:
    """Display the current hand state."""

    clear_terminal()

    table = hand.table

    print("=" * 72)
    print(" TEXAS HOLD'EM ")
    print("=" * 72)

    print(
        f" Street : {hand.street:<8}"
        f" Pot : {hand.pot:<6}"
        f" Current bet : {hand.current_bet}"
    )

    print()

    board = (
        " ".join(f"[{card}]" for card in hand.community_cards)
        if hand.community_cards
        else "-"
    )

    print(f" Board : {board}")

    print()
    print("-" * 72)
    print(f"{'POSITION':<10}{'PLAYER':<15}{'STACK':<10}{'BET':<10}STATUS")
    print("-" * 72)

    for player in table.players:
        status = get_player_status(player)

        position = player.position if player.position is not None else "-"

        print(
            f"{position:<10}"
            f"{player.name:<15}"
            f"{player.stack:<10}"
            f"{player.current_bet:<10}"
            f"{status}"
        )

    print("-" * 72)

    if current_player is not None:
        print()

        cards = " ".join(f"[{card}]" for card in current_player.hand)

        print(f" YOUR TURN — {current_player.name} ({current_player.position})")

        print(f" Hand : {cards}")

        call_amount = max(
            0,
            hand.current_bet - current_player.current_bet,
        )

        if call_amount:
            actual_call_amount = min(
                call_amount,
                current_player.stack,
            )

            if actual_call_amount == current_player.stack:
                print(f" To call : {actual_call_amount} (ALL-IN)")
            else:
                print(f" To call : {actual_call_amount}")

        print()


def get_player_status(
    player: Player,
) -> str:
    """Return a human-readable player status."""

    if player.is_eliminated:
        return "ELIMINATED"

    if player.folded:
        return "FOLDED"

    if player.all_in:
        return "ALL-IN"

    if player.stack == 0:
        return "BUSTED"

    return "ACTIVE"


def ask_player_action(
    player: Player,
    hand: Hand,
    allowed_actions: list[ActionType],
) -> tuple[ActionType, int | None]:
    """Ask the current player for an action."""
    action_mapping: dict[str, ActionType] = {}

    print(f"\n{player.name}'s turn")
    print(f"Stack: {player.stack}")
    print("Available actions:")

    call_amount = max(
        0,
        hand.current_bet - player.current_bet,
    )

    actual_call_amount = min(
        call_amount,
        player.stack,
    )

    minimum_raise = hand.current_bet + hand.last_raise_size

    display_index = 1

    for action in allowed_actions:
        # --------------------------------------------------
        # CALL
        # --------------------------------------------------
        if action == "call":
            action_mapping[str(display_index)] = action

            if actual_call_amount == player.stack:
                print(f"[{display_index}] CALL ALL-IN ({actual_call_amount})")
            else:
                print(f"[{display_index}] CALL ({actual_call_amount})")

            display_index += 1

        # --------------------------------------------------
        # RAISE
        # --------------------------------------------------
        elif action == "raise":
            action_mapping[str(display_index)] = action

            print(f"[{display_index}] RAISE (minimum: {minimum_raise})")

            display_index += 1

        # --------------------------------------------------
        # ALL-IN
        # --------------------------------------------------
        elif action == "all_in":
            # If calling already puts the player all-in,
            # the separate ALL-IN action is redundant.
            if actual_call_amount == player.stack:
                continue

            action_mapping[str(display_index)] = action

            print(f"[{display_index}] ALL-IN ({player.stack})")

            display_index += 1

        # --------------------------------------------------
        # OTHER ACTIONS (fold, check, ...)
        # --------------------------------------------------
        else:
            action_mapping[str(display_index)] = action

            print(f"[{display_index}] {action.upper()}")

            display_index += 1

    while True:
        choice = input("\nAction > ").strip()

        action = action_mapping.get(
            choice,
        )

        if action is None:
            print("Invalid action.")
            continue

        # --------------------------------------------------
        # RAISE
        # --------------------------------------------------
        if action == "raise":
            while True:
                try:
                    amount = int(input("Raise amount: "))

                    if amount <= 0:
                        print("ERROR: Raise amount must be greater than 0.")
                        continue

                    if amount > player.stack:
                        print(
                            f"ERROR: You cannot raise "
                            f"more than your stack "
                            f"({player.stack})."
                        )
                        continue

                    if amount < minimum_raise:
                        print(f"ERROR: Minimum raise is {minimum_raise}.")
                        continue

                    break

                except ValueError:
                    print("ERROR: Please enter a valid amount.")

            return action, amount

        # --------------------------------------------------
        # ALL-IN
        # --------------------------------------------------
        if action == "all_in":
            return action, player.stack

        # --------------------------------------------------
        # CALL / CHECK / FOLD
        # --------------------------------------------------
        return action, None


def ask_player_count(
    max_players: int,
) -> int:
    """
    Ask the user how many players should be seated
    at the table.
    """

    while True:
        print()
        print("=" * 50)
        print(" TEXAS HOLD'EM — NEW SESSION ")
        print("=" * 50)
        print(f"Choose the number of players (2-{max_players}).")

        choice = input("\nNumber of players > ").strip()

        try:
            player_count = int(choice)

        except ValueError:
            print("Please enter a valid number.")
            continue

        if not 2 <= player_count <= max_players:
            print(f"Please choose a number between 2 and {max_players}.")
            continue

        return player_count


def display_hand_result(
    hand: Hand,
) -> None:
    """Display the result of the completed hand."""

    print()
    print("=" * 72)
    print(" HAND RESULT ")
    print("=" * 72)

    if hand.winner_by_fold is not None:
        print(f"\n{hand.winner_by_fold.name} wins by fold.")

    else:
        print("\nSHOWDOWN")

        for player_name, evaluation in hand.showdown_evaluations.items():
            player = next(
                player for player in hand.table.players if player.name == player_name
            )

            if player.is_eliminated:
                continue

            hole_cards = " ".join(f"[{card}]" for card in player.hand)

            used_cards = " ".join(f"[{card}]" for card in evaluation.cards)

            print()
            print(f"  {player_name}")
            print(f"    Hand       : {hole_cards}")
            print(f"    Best hand  : {evaluation.name}")
            print(f"    Cards used : {used_cards}")

        print()
        print("POTS")

        for index, pot_result in enumerate(
            hand.pot_results,
            start=1,
        ):
            winners = ", ".join(
                pot_result.winners,
            )

            print(f"  Pot {index}: {pot_result.amount} -> {winners}")

            if pot_result.decisive_tiebreaker is not None:
                print(
                    f"    Decisive: "
                    f"{pot_result.decisive_tiebreaker} "
                    f"({pot_result.decisive_value})"
                )

    print()
    print("PAYOUTS")

    for player_name, amount in hand.payouts.items():
        print(f"  {player_name}: +{amount}")

    print()
    print("STACKS")

    for player in hand.table.players:
        print(f"  {player.name}: {player.stack}")
