# backend/game/models/action_types.py

from __future__ import annotations

from dataclasses import dataclass

from ..constants import ActionType


@dataclass(frozen=True)
class Action:
    """An action requested by a player."""

    type: ActionType
    amount: int | None = None


@dataclass(frozen=True)
class LegalAction:
    """An action currently available to a player."""

    type: ActionType
    amount: int | None = None
    min_amount: int | None = None
    max_amount: int | None = None
