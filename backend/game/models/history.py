from __future__ import annotations

from .models import (
    ActionEvent,
    Hand,
    Player,
    PotEvent,
    StreetEvent,
)


def record_action(
    hand: Hand,
    player: Player,
    action: str,
    amount: int,
    bet_before: int,
    bet_initiator: bool = False,
) -> None:
    """Record one player action."""

    event = ActionEvent(
        sequence=len(hand.actions) + 1,
        street=hand.street,
        player=player.name,
        position=player.position,
        action=action,
        amount=amount,
        bet_before=bet_before,
        bet_after=player.current_bet,
        pot_after=hand.pot,
        current_bet_after=hand.current_bet,
        bet_initiator=bet_initiator,
    )

    hand.actions.append(event)

    hand.pot_history.append(
        PotEvent(
            sequence=event.sequence,
            street=hand.street,
            amount=hand.pot,
        )
    )


def record_street(
    hand: Hand,
) -> None:
    """Record the current street and community cards."""

    hand.streets.append(
        StreetEvent(
            street=hand.street,
            community_cards=tuple(hand.community_cards),
        )
    )
