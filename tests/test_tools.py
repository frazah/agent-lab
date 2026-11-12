import json
import shutil
from pathlib import Path

import pytest

from store import NoteStore
from tools import dispatch

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "base_notes"


@pytest.fixture
def store(tmp_path):
    # A fresh copy of the notes for every test.
    shutil.copytree(FIXTURE_PATH, tmp_path / "notes")
    return NoteStore(path=tmp_path / "notes")


def test_search_returns_json_list(store):
    out = dispatch(store, "search_notes", {"query": "allenamento"})
    results = json.loads(out)
    ids = {r["note_id"] for r in results}
    assert "allenamento-palestra-scheda-a" in ids
    assert set(results[0]) == {"note_id", "title", "sample"}


def test_search_no_match_returns_empty_list(store):
    assert json.loads(dispatch(store, "search_notes", {"query": "zzz-nessuna"})) == []


def test_get_note_returns_full_note(store):
    note = json.loads(dispatch(store, "get_note", {"note_id": "allenamento-palestra-scheda-a"}))
    assert note["title"] == "Allenamento palestra - Scheda A"
    assert note["tags"] == ["palestra", "salute"]
    assert "Panca piana" in note["content"]


# Errors must come back as text for the model, never as exceptions.
def test_get_missing_note_is_error_message(store):
    out = dispatch(store, "get_note", {"note_id": "xyz"})
    assert out.startswith("Error:")
    assert "xyz" in out


def test_path_traversal_is_error_message(store):
    out = dispatch(store, "get_note", {"note_id": "../secret"})
    assert out.startswith("Error:")


def test_delete_note(store):
    out = dispatch(store, "delete_note", {"note_id": "todo-settimana"})
    assert "todo-settimana" in out
    assert dispatch(store, "get_note", {"note_id": "todo-settimana"}).startswith("Error:")


def test_unknown_tool_is_error_message(store):
    out = dispatch(store, "rename_note", {})
    assert out.startswith("Error:")
    assert "search_notes" in out


def test_missing_argument_is_error_message(store):
    out = dispatch(store, "get_note", {})
    assert out.startswith("Error:")
    assert "note_id" in out
