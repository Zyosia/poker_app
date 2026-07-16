# game/engine.py

from game.deck import Deck

from game.session import (
    GameConfig,
    create_session
)

from game.betting import betting_round

from game.terminal_ui import display_table

from game.helper import wait


def deal_hole_cards(table, deck):

    for _ in range(2):

        for player in table.players:

            player.hand.append(
                deck.draw()
            )


def deal_flop(table, deck):

    deck.burn()

    for _ in range(3):
        table.community_cards.append(
            deck.draw()
        )

    table.street = "FLOP"


def deal_turn(table, deck):

    deck.burn()

    table.community_cards.append(
        deck.draw()
    )

    table.street = "TURN"


def deal_river(table, deck):

    deck.burn()

    table.community_cards.append(
        deck.draw()
    )

    table.street = "RIVER"


def main():

    config = GameConfig(
        starting_stack=1000,
        small_blind=5,
        big_blind=10,
        max_players=6
    )

    player_names = [
        "Alice",
        "Bob",
        "Charlie"
    ]

    table = create_session(
        player_names,
        config
    )

    deck = Deck()

    deal_hole_cards(table, deck)

    display_table(table)

    wait()

    # PREFLOP
    betting_round(table)

    # FLOP
    deal_flop(table, deck)

    betting_round(table)

    # TURN
    deal_turn(table, deck)

    betting_round(table)

    # RIVER
    deal_river(table, deck)

    betting_round(table)

    display_table(table)

    print("\nHand finished.")


if __name__ == "__main__":
    main()