# game/engine.py

from __future__ import annotations

from .hand import start_hand
from .helper import wait
from .session import (
    GameConfig,
    GameSession,
    create_session,
)
from .terminal_ui import (
    ask_player_count,
    display_hand_result,
    display_table,
)


def handle_rebuys(
    session: GameSession,
) -> None:
    """Ask busted players whether they want to rebuy."""

    busted_players = session.get_busted_players()

    for player in busted_players:
        print()
        print(f"{player.name} has busted.")

        while True:
            choice = (
                input(
                    f"Rebuy for {player.name} "
                    f"({session.config.rebuy_stack} chips)? "
                    "[y/n] > "
                )
                .strip()
                .lower()
            )

            if choice in {"y", "yes"}:
                session.rebuy_player(player)
                player.eliminated = False
                print(f"{player.name} rebought for {session.config.rebuy_stack} chips.")

                break

            if choice in {"n", "no"}:
                player.eliminated = True
                print(f"{player.name} is eliminated.")
                break

            print("Please answer y or n.")


def start_session() -> GameSession:
    """Create and run a complete poker session."""

    config = GameConfig(
        starting_stack=1000,
        small_blind=5,
        big_blind=10,
        max_players=6,
    )

    player_count = ask_player_count(
        max_players=config.max_players,
    )

    player_names = [
        f"Player{i}"
        for i in range(
            1,
            player_count + 1,
        )
    ]

    session = create_session(
        player_names=player_names,
        config=config,
    )

    print()
    print(f"Starting session with {player_count} players.")

    wait()

    while session.can_continue():
        print()
        print(f"Starting Hand #{session.hand_number + 1}")

        hand = start_hand(
            session=session,
        )

        display_table(
            hand=hand,
        )

        display_hand_result(
            hand=hand,
        )

        handle_rebuys(
            session=session,
        )

        wait()

        if session.can_continue():
            session.table.move_dealer()

    print()
    print("=" * 72)
    print(" SESSION FINISHED ")
    print("=" * 72)

    remaining_players = session.get_players_with_chips()

    if remaining_players:
        winner = remaining_players[0]

        print(f"\n{winner.name} wins the session.")

    return session


if __name__ == "__main__":
    start_session()
