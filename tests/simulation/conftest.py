"""Fixtures of the simulation tests."""

import pytest

from backend.simulation import runner
from backend.simulation.events import HandObserver
from tests.simulation.helpers import AttachObserver


@pytest.fixture
def attach_observer(monkeypatch: pytest.MonkeyPatch) -> AttachObserver:
    """Attach an observer to every table the runner creates."""
    observers: list[HandObserver] = []
    original = runner.ArenaTable

    def table_with_observers(*args: object, **kwargs: object) -> runner.ArenaTable:
        table = original(*args, **kwargs)  # type: ignore[arg-type]
        table.observers.extend(observers)
        return table

    monkeypatch.setattr(runner, "ArenaTable", table_with_observers)

    return observers.append
