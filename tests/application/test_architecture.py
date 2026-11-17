"""Checks on the dependency direction between the layers."""

import subprocess
import sys

BACKEND_MODULES = (
    "backend.poker_engine.hand",
    "backend.application.game",
    "backend.application.setup",
    "backend.application.tournament",
    "backend.application.hand_records",
    "backend.application.replay",
    "backend.application.equity",
    "backend.application.ranges",
    "backend.application.hand_import",
    "backend.application.profile",
    "backend.bots.basic_bot",
    "backend.bots.random_bot",
    "backend.bots.factory",
    "backend.simulation.runner",
    "backend.simulation.my_stats",
)
APPLICATION_MODULES = tuple(
    name for name in BACKEND_MODULES if name.startswith("backend.application.")
)


def test_backend_does_not_depend_on_the_graphical_framework() -> None:
    script = (
        "import sys, importlib\n"
        f"for name in {BACKEND_MODULES!r}:\n"
        "    importlib.import_module(name)\n"
        "loaded = [m for m in sys.modules if m.startswith(('PySide6', 'frontend'))]\n"
        "assert not loaded, loaded\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_engine_does_not_depend_on_the_application_or_bots() -> None:
    script = (
        "import sys, importlib\n"
        "importlib.import_module('backend.poker_engine.hand')\n"
        "importlib.import_module('backend.poker_engine.showdown')\n"
        "loaded = [m for m in sys.modules\n"
        "          if m.startswith(('backend.application.', 'backend.bots.',\n"
        "                           'backend.simulation.'))]\n"
        "assert not loaded, loaded\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_application_does_not_depend_on_the_simulation() -> None:
    """The simulation uses the application layer, never the other way."""
    script = (
        "import sys, importlib\n"
        f"for name in {APPLICATION_MODULES!r}:\n"
        "    importlib.import_module(name)\n"
        "loaded = [m for m in sys.modules if m.startswith('backend.simulation')]\n"
        "assert not loaded, loaded\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
