"""Tests for tools.py: the argument models, the generated schemas and dispatch.

The `store` and `secret_file` fixtures come from conftest.py.
"""

import json
from typing import Any, cast

import pytest
from pydantic import ValidationError

from store import InvalidNoteIdError

from tools import (
    ID_PATTERN,
    MAX_QUERY_LENGTH,
    TOOLS,
    DeleteNoteArgs,
    GetNoteArgs,
    SearchNotesArgs,
    ToolOutput,
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
    out = dispatch(store, "search_notes", {"query": "allenamento"})
    assert out.error_type is None
    results = json.loads(out.text)
    ids = {r["note_id"] for r in results}
    assert "allenamento-palestra-scheda-a" in ids
    assert set(results[0]) == {"note_id", "title", "sample"}


def test_search_no_match_returns_empty_list(store):
    out = dispatch(store, "search_notes", {"query": "zzz-nessuna"})
    assert out.error_type is None
    assert json.loads(out.text) == []


def test_get_note_returns_full_note(store):
    out = dispatch(store, "get_note", {"note_id": "allenamento-palestra-scheda-a"})
    assert out.error_type is None
    note = json.loads(out.text)
    assert note["title"] == "Allenamento palestra - Scheda A"
    assert note["tags"] == ["palestra", "salute"]
    assert "Panca piana" in note["content"]


def test_delete_note(store):
    out = dispatch(store, "delete_note", {"note_id": "todo-settimana"})
    assert out == ToolOutput("Note deleted: todo-settimana")
    assert dispatch(store, "get_note", {"note_id": "todo-settimana"}).error_type == "not_found"


# Dispatch: errors come back as a ToolOutput with an error_type, never as exceptions.
# The model only reads `text`, so it must still say what went wrong.

def test_get_missing_note_is_not_found(store):
    out = dispatch(store, "get_note", {"note_id": "xyz"})
    assert out.error_type == "not_found"
    assert out.text.startswith("Error:")
    assert "xyz" in out.text


def test_delete_missing_note_is_not_found(store):
    out = dispatch(store, "delete_note", {"note_id": "xyz"})
    assert out.error_type == "not_found"
    assert len(list(store.path.glob("*.md"))) == 18


def test_unknown_tool(store):
    out = dispatch(store, "rename_note", {})
    assert out.error_type == "unknown_tool"
    assert "search_notes" in out.text  # tells the model which tools exist


def test_missing_argument_is_invalid_arguments(store):
    out = dispatch(store, "get_note", {})
    assert out.error_type == "invalid_arguments"
    assert "note_id" in out.text


def test_extra_field_is_invalid_arguments(store):
    out = dispatch(store, "get_note", {"note_id": "viaggio-lisbona", "force": True})
    assert out.error_type == "invalid_arguments"
    assert "force" in out.text


def test_path_traversal_stopped_by_validation(store):
    # Pydantic stops it before it reaches the store, so it is invalid_arguments,
    # not invalid_id. The store's own check is tested in test_store.py.
    out = dispatch(store, "get_note", {"note_id": "../secret"})
    assert out.error_type == "invalid_arguments"


def test_delete_path_traversal_deletes_nothing(store, secret_file):
    out = dispatch(store, "delete_note", {"note_id": "../secret"})
    assert out.error_type == "invalid_arguments"
    assert secret_file.exists()
    assert len(list(store.path.glob("*.md"))) == 18


def test_store_invalid_id_is_invalid_id(store, monkeypatch):
    # With today's ID_PATTERN no id passes validation and then fails the
    # store's check, so we make the store raise it to test the except branch.
    def raise_invalid(note_id):
        raise InvalidNoteIdError(note_id)

    monkeypatch.setattr(store, "get_note", raise_invalid)
    out = dispatch(store, "get_note", {"note_id": "viaggio-lisbona"})
    assert out.error_type == "invalid_id"
    assert out.text.startswith("Error:")


# The delete check: dispatch asks confirm_delete before deleting, if one is given.

def _recorder(answer: bool):
    """A confirm_delete that always gives `answer` and remembers the ids it was asked about."""
    asked: list[str] = []

    def confirm(note_id: str) -> bool:
        asked.append(note_id)
        return answer

    return confirm, asked


def test_delete_refused_is_blocked_and_keeps_the_note(store):
    out = dispatch(store, "delete_note", {"note_id": "todo-settimana"}, lambda note_id: False)
    assert out.error_type == "blocked"
    assert out.text.startswith("Error:")
    assert "todo-settimana" in out.text
    assert "todo-settimana" in store.list_note_ids()


def test_delete_confirmed_deletes_the_note(store):
    out = dispatch(store, "delete_note", {"note_id": "todo-settimana"}, lambda note_id: True)
    assert out == ToolOutput("Note deleted: todo-settimana")
    assert "todo-settimana" not in store.list_note_ids()


def test_delete_without_check_deletes_as_before(store):
    out = dispatch(store, "delete_note", {"note_id": "todo-settimana"}, None)
    assert out == ToolOutput("Note deleted: todo-settimana")
    assert "todo-settimana" not in store.list_note_ids()


def test_invalid_id_is_rejected_before_asking(store, secret_file):
    # No point asking the user whether to delete "../secret".
    confirm, asked = _recorder(True)
    out = dispatch(store, "delete_note", {"note_id": "../secret"}, confirm)
    assert out.error_type == "invalid_arguments"
    assert asked == []
    assert secret_file.exists()


def test_missing_note_is_not_found_before_asking(store):
    # No point asking the user to confirm deleting a note that doesn't exist.
    confirm, asked = _recorder(True)
    out = dispatch(store, "delete_note", {"note_id": "xyz"}, confirm)
    assert out.error_type == "not_found"
    assert asked == []


def test_confirm_gets_the_id_the_model_asked_for(store):
    confirm, asked = _recorder(False)
    dispatch(store, "delete_note", {"note_id": "viaggio-lisbona"}, confirm)
    assert asked == ["viaggio-lisbona"]


def test_other_tools_never_ask(store):
    confirm, asked = _recorder(False)
    dispatch(store, "search_notes", {"query": "ricetta"}, confirm)
    dispatch(store, "get_note", {"note_id": "viaggio-lisbona"}, confirm)
    assert asked == []
