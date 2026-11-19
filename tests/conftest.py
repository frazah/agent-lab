"""Fixtures for every test: pytest loads this file on its own, so a test only
has to name `store` or `secret_file` as a parameter to get them."""

import shutil

import pytest

from helpers import BASE_NOTES
from store import NoteStore


@pytest.fixture
def store(tmp_path):
    # A fresh copy of the notes for every test, so tests can delete freely.
    shutil.copytree(BASE_NOTES, tmp_path / "notes")
    return NoteStore(path=tmp_path / "notes")


@pytest.fixture
def secret_file(tmp_path):
    # A valid note next to the notes folder, outside it: tmp_path/secret.md.
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
