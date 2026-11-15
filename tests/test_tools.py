"""Tests for tools.py: the argument models, the generated schemas and dispatch.

The `store` and `secret_file` fixtures come from conftest.py.
"""

import json
from typing import Any, cast

import pytest
from pydantic import ValidationError

from tools import (
    ID_PATTERN,
    MAX_QUERY_LENGTH,
    TOOLS,
    DeleteNoteArgs,
    GetNoteArgs,
    SearchNotesArgs,
    dispatch,
)


# The Pydantic models on their own

def test_valid_id_passes():
    args = GetNoteArgs.model_validate({"note_id": "viaggio-lisbona"})
    assert args.note_id == "viaggio-lisbona"


def test_missing_note_id_is_rejected():
    with pytest.raises(ValidationError):
        GetNoteArgs.model_validate({})


def test_extra_field_is_rejected():
    with pytest.raises(ValidationError):
        GetNoteArgs.model_validate({"note_id": "viaggio-lisbona", "extra": "x"})


def test_number_instead_of_string_is_rejected():
    with pytest.raises(ValidationError):
        GetNoteArgs.model_validate({"note_id": 42})


def test_path_traversal_id_is_rejected():
    with pytest.raises(ValidationError):
        GetNoteArgs.model_validate({"note_id": "../segreto"})


def test_uppercase_id_is_rejected():
    with pytest.raises(ValidationError):
        GetNoteArgs.model_validate({"note_id": "Viaggio-Lisbona"})


def test_delete_args_reject_path_traversal():
    # delete is the tool that can do damage: it needs the same id rules.
    with pytest.raises(ValidationError):
        DeleteNoteArgs.model_validate({"note_id": "../segreto"})


def test_empty_query_is_rejected():
    with pytest.raises(ValidationError):
        SearchNotesArgs.model_validate({"query": ""})


def test_too_long_query_is_rejected():
    with pytest.raises(ValidationError):
        SearchNotesArgs.model_validate({"query": "a" * (MAX_QUERY_LENGTH + 1)})


# The schemas the model sees

def _schema(name: str) -> dict[str, Any]:
    # The SDK types input_schema as a TypedDict that only knows a few keys;
    # at runtime it is the plain dict Pydantic generated.
    tool = next(t for t in TOOLS if t["name"] == name)
    return cast(dict[str, Any], tool["input_schema"])


def test_every_tool_has_a_schema():
    assert {t["name"] for t in TOOLS} == {"search_notes", "get_note", "delete_note"}


def test_schema_tells_the_model_the_id_format():
    # The old hand-written schema had no pattern: the model only found out
    # the id format by getting an error.
    for name in ("get_note", "delete_note"):
        schema = _schema(name)
        assert schema["properties"]["note_id"]["pattern"] == ID_PATTERN
        assert schema["required"] == ["note_id"]


def test_schema_forbids_extra_fields():
    for tool in TOOLS:
        assert _schema(tool["name"])["additionalProperties"] is False


# Dispatch: normal calls

def test_search_returns_json_list(store):
    results = json.loads(dispatch(store, "search_notes", {"query": "allenamento"}))
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


def test_delete_note(store):
    out = dispatch(store, "delete_note", {"note_id": "todo-settimana"})
    assert out == "Note deleted: todo-settimana"
    assert dispatch(store, "get_note", {"note_id": "todo-settimana"}).startswith("Error:")


# Dispatch: errors come back as text, never as exceptions

def test_get_missing_note_is_error_message(store):
    out = dispatch(store, "get_note", {"note_id": "xyz"})
    assert out.startswith("Error:")
    assert "xyz" in out


def test_unknown_tool_is_error_message(store):
    out = dispatch(store, "rename_note", {})
    assert out.startswith("Error:")
    assert "search_notes" in out


def test_missing_argument_is_error_message(store):
    out = dispatch(store, "get_note", {})
    assert out.startswith("Error: invalid arguments")
    assert "note_id" in out


def test_extra_field_is_error_message(store):
    out = dispatch(store, "get_note", {"note_id": "viaggio-lisbona", "force": True})
    assert out.startswith("Error: invalid arguments")
    assert "force" in out


def test_path_traversal_stopped_by_validation(store):
    # Pydantic stops it before it reaches the store. The store's own check
    # is tested in test_store.py.
    out = dispatch(store, "get_note", {"note_id": "../secret"})
    assert out.startswith("Error: invalid arguments")


def test_delete_path_traversal_deletes_nothing(store, secret_file):
    out = dispatch(store, "delete_note", {"note_id": "../secret"})
    assert out.startswith("Error:")
    assert secret_file.exists()
    assert len(list(store.path.glob("*.md"))) == 18
