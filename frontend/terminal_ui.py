"""Minimal terminal front-end: one human player against bots.

Run with ``python -m frontend.terminal_ui``.
"""

import os

from backend.application.controllers import DecisionContext, PlayerController
from backend.application.game import PokerGame
from backend.application.persistence import new_session_file_path
from backend.bots.basic_bot import BasicBot
from backend.poker_engine.actions import Action, LegalAction
from backend.poker_engine.constants import MAX_TABLE_SEATS, ActionType
from backend.poker_engine.models import Hand, Player
from backend.poker_engine.session import GameConfig, GameSession, create_session

HUMAN_NAME = "Hero"
LINE_WIDTH = 72


class TerminalController(PlayerController):
    """Asks the user for a decision on the command line."""

    is_human = True

    def choose_action(self, context: DecisionContext) -> Action:
        cards = " ".join(f"[{card}]" for card in context.hole_cards)
        print(f"\n YOUR TURN - Hand: {cards}  Stack: {context.player.stack}")

        for index, legal_action in enumerate(context.legal_actions, start=1):
            print(f" [{index}] {describe_legal_action(legal_action)}")

        legal_action = ask_choice(context.legal_actions)

        if legal_action.type != ActionType.RAISE:
            return Action(type=legal_action.type)

        return Action(type=ActionType.RAISE, amount=ask_raise_amount(legal_action))


def describe_legal_action(legal_action: LegalAction) -> str:
    """Return the menu label of a legal action."""
    label = legal_action.type.replace("_", "-").upper()

    if legal_action.type == ActionType.RAISE:
        return f"{label} to {legal_action.min_amount}-{legal_action.max_amount}"

    if legal_action.amount is not None:
        return f"{label} ({legal_action.amount})"

    return label


def ask_choice(legal_actions: tuple[LegalAction, ...]) -> LegalAction:
    """Ask the user to pick one of the legal actions."""
    while True:
        choice = input("\n Action > ").strip()

        if choice.isdigit() and 1 <= int(choice) <= len(legal_actions):
            return legal_actions[int(choice) - 1]

        print(" Invalid action.")


def ask_raise_amount(legal_action: LegalAction) -> int:
    """Ask the user for a "raise to" amount within the legal range."""
    minimum = legal_action.min_amount
    maximum = legal_action.max_amount
    assert minimum is not None and maximum is not None

    while True:
        choice = input(f" Raise to ({minimum}-{maximum}) > ").strip()

        if choice.isdigit() and minimum <= int(choice) <= maximum:
            return int(choice)

        print(f" Please enter an amount between {minimum} and {maximum}.")


def ask_player_count(max_players: int) -> int:
    """Ask the user how many players should be seated at the table."""
    while True:
        choice = input(f"\n Number of players (2-{max_players}) > ").strip()

        if choice.isdigit() and 2 <= int(choice) <= max_players:
            return int(choice)

        print(f" Please choose a number between 2 and {max_players}.")


def clear_terminal() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def get_player_status(player: Player) -> str:
    """Return a human-readable player status."""
    if player.is_eliminated:
        return "ELIMINATED"

    if player.folded:
        return "FOLDED"

    if player.all_in:
        return "ALL-IN"

    return "ACTIVE"


def display_table(hand: Hand) -> None:
    """Display the current hand state."""
    clear_terminal()

    board = " ".join(f"[{card}]" for card in hand.community_cards) or "-"

    print("=" * LINE_WIDTH)
    print(" TEXAS HOLD'EM ")
    print("=" * LINE_WIDTH)
    print(f" Street: {hand.street:<8} Pot: {hand.pot:<6} Bet: {hand.current_bet}")
    print(f"\n Board: {board}\n")
    print("-" * LINE_WIDTH)
    print(f"{'POSITION':<10}{'PLAYER':<15}{'STACK':<10}{'BET':<10}STATUS")
    print("-" * LINE_WIDTH)

    for player in hand.table.players:
        print(
            f"{player.position or '-':<10}"
            f"{player.name:<15}"
            f"{player.stack:<10}"
            f"{player.current_bet:<10}"
            f"{get_player_status(player)}"
        )

    print("-" * LINE_WIDTH)

    for event in hand.actions[-len(hand.table.players) :]:
        print(f" {event.player}: {event.action} {event.amount or ''}")


def display_hand_result(hand: Hand) -> None:
    """Display the result of the completed hand."""
    print("\n" + "=" * LINE_WIDTH)
    print(" HAND RESULT ")
    print("=" * LINE_WIDTH)

    if hand.winner_by_fold is not None:
        print(f"\n {hand.winner_by_fold.name} wins by fold.")
    else:
        hole_cards = {player.name: player.hand for player in hand.table.players}

        for player_name, evaluation in hand.showdown_evaluations.items():
            cards = " ".join(f"[{card}]" for card in hole_cards[player_name])
            print(f"\n {player_name}: {cards} - {evaluation.name}")

        for index, pot_result in enumerate(hand.pot_results, start=1):
            winners = ", ".join(pot_result.winners)
            print(f"\n Pot {index}: {pot_result.amount} -> {winners}")

    print("\n STACKS")

    for player in hand.table.players:
        won = hand.payouts.get(player.name, 0)
        suffix = f" (+{won})" if won else ""
        print(f"  {player.name}: {player.stack}{suffix}")


def handle_rebuys(session: GameSession) -> None:
    """Ask every busted player whether to rebuy or leave the table.

    Busted bots are already eliminated by the game when a hand finishes.
    """
    for player in session.get_busted_players():
        while True:
            choice = input(
                f"\n {player.name} has busted. "
                f"Rebuy for {session.config.rebuy_stack} chips? [y/n] > "
            )
            choice = choice.strip().lower()

            if choice in {"y", "yes"}:
                session.rebuy_player(player)
                break

            if choice in {"n", "no"}:
                session.eliminate_player(player)
                break

            print(" Please answer y or n.")


def run_session() -> None:
    """Create and run a complete poker session in the terminal."""
    print("=" * LINE_WIDTH)
    print(" TEXAS HOLD'EM - NEW SESSION ")
    print("=" * LINE_WIDTH)

    player_count = ask_player_count(MAX_TABLE_SEATS)
    bot_names = [f"Bot{index}" for index in range(1, player_count)]

    session = create_session(
        player_names=[HUMAN_NAME, *bot_names],
        config=GameConfig(),
    )
    controllers: dict[str, PlayerController] = {name: BasicBot() for name in bot_names}
    controllers[HUMAN_NAME] = TerminalController()

    game = PokerGame(
        session=session,
        controllers=controllers,
        save_path=new_session_file_path(),
    )
    human = session.players[0]

    while game.can_start_hand() and not human.is_eliminated:
        hand = game.start_hand()

        while not hand.finished:
            display_table(hand)
            game.step()

        display_table(hand)
        display_hand_result(hand)
        handle_rebuys(session)
        input("\n Press ENTER to continue...")

    print("\n" + "=" * LINE_WIDTH)
    print(" SESSION FINISHED ")
    print("=" * LINE_WIDTH)

    for player in sorted(session.players, key=lambda p: p.stack, reverse=True):
        print(f"  {player.name}: {player.stack}")


if __name__ == "__main__":
    run_session()
