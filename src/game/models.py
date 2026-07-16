# game/models.py

class Player:
    def __init__(self, name, stack):
        self.name = name
        self.stack = stack

        self.hand = []

        self.current_bet = 0

        self.folded = False
        self.all_in = False

        self.position = None

    def reset_for_new_hand(self):
        self.hand = []
        self.current_bet = 0
        self.folded = False
        self.all_in = False

    def __str__(self):
        return f"{self.name} ({self.stack})"


class Table:
    def __init__(self):
        self.players = []

        self.community_cards = []

        self.pot = 0

        self.current_bet = 0

        self.dealer_position = 0

        self.street = "PREFLOP"

    def reset_for_new_hand(self):
        self.community_cards = []
        self.pot = 0
        self.current_bet = 0
        self.street = "PREFLOP"

        for player in self.players:
            player.reset_for_new_hand()