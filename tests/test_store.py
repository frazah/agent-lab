"""Tests for store.py. The `store` and `secret_file` fixtures come from conftest.py."""

from pathlib import Path

import pytest

from store import InvalidNoteIdError, NoteNotFoundError

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "base_notes"


# Reading

def test_get_note_existing(store):
    note = store.get_note("spesa-settimana-1")
    assert note.title == "Spesa settimana 1"


def test_get_note_content_and_tags(store):
    note = store.get_note("spesa-settimana-1")
    assert "Latte" in note.content
    assert note.tags == ["spesa", "casa"]


def test_get_note_keeps_dashes_in_body(store):
    # "---" in the body is a Markdown horizontal rule, not a new header.
    (store.path / "con-righello.md").write_text(
        "---\ntitle: Righello\ntags: prova\ndate: 2026-11-16\n---\nSopra\n---\nSotto\n",
        encoding="utf-8",
    )
    note = store.get_note("con-righello")
    assert note.content == "Sopra\n---\nSotto"


def test_get_note_missing(store):
    with pytest.raises(NoteNotFoundError):
        store.get_note("non-existent-note")


def test_list_note_ids_is_sorted(store):
    ids = store.list_note_ids()
    assert len(ids) == 18
    assert ids == sorted(ids)


# Searching

def test_search_notes(store):
    assert len(store.search_notes("allenamento")) == 4


def test_search_is_case_insensitive(store):
    assert len(store.search_notes("ALLENAMENTO")) == 4


def test_search_no_results(store):
    assert store.search_notes("non-existent-query") == []


def test_search_includes_tags(store):
    # The pancake note has "palestra" only as a tag, not in its title or body.
    results = store.search_notes("palestra")
    ids = {r.note_id for r in results}
    assert len(results) == 3
    assert "ricetta-pancake-proteici" in ids


def test_search_only_content(store):
    assert len(store.search_notes("squat")) == 1


# Deleting

def test_delete_note(store):
    store.delete_note("spesa-settimana-1")
    with pytest.raises(NoteNotFoundError):
        store.get_note("spesa-settimana-1")


def test_delete_note_not_found(store):
    with pytest.raises(NoteNotFoundError):
        store.delete_note("wrong-note-id")


def test_delete_touches_only_the_copy(store):
    store.delete_note("spesa-settimana-1")
    assert (FIXTURE_PATH / "spesa-settimana-1.md").exists()


# Path traversal: the store checks ids on its own, even without Pydantic in front

def test_get_note_blocks_path_traversal(store, secret_file):
    with pytest.raises(InvalidNoteIdError):
        store.get_note("../secret")


def test_delete_note_blocks_path_traversal(store, secret_file):
    with pytest.raises(InvalidNoteIdError):
        store.delete_note("../secret")
    assert secret_file.exists()
