"""Consistency checks run on every simulated hand."""

from collections.abc import Mapping

from backend.poker_engine.models import Hand


class InvariantError(RuntimeError):
    """A simulated hand broke an invariant of the engine.

    It carries everything needed to replay the hand exactly with
    ``backend.simulation.runner.replay_hand``.
    """

    def __init__(
        self,
        message: str,
        seed: int,
        hand_index: int,
        session_index: int | None = None,
    ) -> None:
        # Every argument goes to ``args`` so the error survives pickling
        # between worker processes.
        super().__init__(message, seed, hand_index, session_index)
        self.message = message
        self.seed = seed
        self.hand_index = hand_index
        self.session_index = session_index

    def __str__(self) -> str:
        location = f"hand_index={self.hand_index}"

        if self.session_index is not None:
            location = f"session_index={self.session_index}, {location}"

        return (
            f"{self.message} (seed={self.seed}, {location}). "
            f"Replay it with replay_hand(config, {location})."
        )


def find_chip_violations(hand: Hand, stacks_before: Mapping[str, int]) -> list[str]:
    """Return a description of every chip accounting problem of a finished hand.

    ``stacks_before`` holds the stacks of the players dealt in, before the
    blinds were posted.
    """
    problems: list[str] = []
    dealt_in = [player for player in hand.table.players if player.name in stacks_before]

    if not hand.finished:
        problems.append("the hand is not finished")

    if hand.pot != 0:
        problems.append(f"{hand.pot} chips are left in the pot")

    chips_before = sum(stacks_before.values())
    chips_after = sum(player.stack for player in dealt_in)

    if chips_after != chips_before:
        problems.append(
            f"chips are not conserved: {chips_before} before, {chips_after} after"
        )

    contributed = hand.dead_money + sum(
        player.total_contribution for player in dealt_in
    )
    paid_out = sum(hand.payouts.values())

    if paid_out != contributed:
        problems.append(f"{paid_out} chips paid out for {contributed} contributed")

    problems.extend(
        f"{player.name} has a negative stack ({player.stack})"
        for player in dealt_in
        if player.stack < 0
    )

    return problems
