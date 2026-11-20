"""Where the data are saved: the sources and a build each have their own (V3.2)."""

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from backend.application.persistence import SESSION_DIR
from frontend import main


def test_run_from_the_sources_is_not_a_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert not main.is_built()

    monkeypatch.setattr(sys, "frozen", True, raising=False)  # As PyInstaller does.
    assert main.is_built()


def test_a_build_keeps_its_sessions_in_its_data_folder(tmp_path: Path) -> None:
    assert main.session_folder(tmp_path, built=True) == tmp_path / "sessions"


def test_the_sources_keep_their_sessions_beside_the_code(tmp_path: Path) -> None:
    assert main.session_folder(tmp_path, built=False) == SESSION_DIR
    assert main.session_folder(None, built=True) == SESSION_DIR


def test_a_build_and_the_sources_use_different_data_folders(
    qapp: QApplication,
) -> None:
    name = qapp.applicationName()

    try:
        qapp.setApplicationName(main.APP_NAME)
        sources = main.data_folder()
        qapp.setApplicationName(main.BUILT_APP_NAME)
        built = main.data_folder()
    finally:
        qapp.setApplicationName(name)

    assert sources is not None and built is not None
    assert sources != built
    assert built.name == main.BUILT_APP_NAME
