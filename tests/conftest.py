"""Fixtures shared by all test files.

pytest loads this file automatically: every test in tests/ can ask for
`store` just by naming it as a parameter, without importing anything.
"""

import shutil
from pathlib import Path

import pytest

from store import NoteStore

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "base_notes"


@pytest.fixture
def store(tmp_path):
    # A fresh copy of the notes for every test: tests can delete freely.
    shutil.copytree(FIXTURE_PATH, tmp_path / "notes")
    return NoteStore(path=tmp_path / "notes")


@pytest.fixture
def secret_file(tmp_path):
    # A valid note OUTSIDE the notes folder, next to it: tmp_path/secret.md.
    path = tmp_path / "secret.md"
    path.write_text(
        "---\n"
        "title: Secret\n"
        "tags: segreto\n"
        "date: 2026-11-06\n"
        "---\n"
        "Questo file sta FUORI dalla cartella delle note.\n"
    )
    return path
