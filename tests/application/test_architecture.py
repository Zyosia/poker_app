"""Checks on the dependency direction between the layers."""

import subprocess
import sys

BACKEND_MODULES = (
    "backend.poker_engine.hand",
    "backend.application.game",
    "backend.application.setup",
    "backend.bots.basic_bot",
    "backend.bots.random_bot",
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
        "          if m.startswith(('backend.application.', 'backend.bots.'))]\n"
        "assert not loaded, loaded\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
