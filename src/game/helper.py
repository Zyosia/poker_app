# game/helper.py

import os


def clear_terminal():
    os.system(
        "cls" if os.name == "nt" else "clear"
    )


def wait():
    input("\nPress ENTER to continue...")