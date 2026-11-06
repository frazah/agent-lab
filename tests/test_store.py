import pytest
import shutil
from pathlib import Path
from store import NoteStore, NoteNotFoundError, InvalidNoteIdError

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "base_notes"

@pytest.fixture
def get_temp_store(tmp_path):
    # Copy the contents of the fixtures directory to the temporary path
    shutil.copytree(FIXTURE_PATH, tmp_path / "notes")
    store = NoteStore(path=tmp_path / "notes")
    return store


@pytest.fixture
def secret_file(tmp_path):
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


def test_get_note_blocks_path_traversal(get_temp_store, secret_file):
    with pytest.raises(InvalidNoteIdError):
        get_temp_store.get_note("../secret")


def test_delete_note_blocks_path_traversal(get_temp_store, secret_file):
    with pytest.raises(InvalidNoteIdError):
        get_temp_store.delete_note("../secret")
    assert secret_file.exists()


def test_get_note_existing(get_temp_store):
    note = get_temp_store.get_note("spesa-settimana-1")
    assert note.title == "Spesa settimana 1"


def test_get_note_missing(get_temp_store):
    with pytest.raises(NoteNotFoundError):
            get_temp_store.get_note("non-existent-note")


def test_get_note_content_and_tags(get_temp_store):
    note = get_temp_store.get_note("spesa-settimana-1")
    assert "Latte" in note.content
    assert note.tags == ["spesa", "casa"]


def test_search_notes(get_temp_store):
    lowercase_results = get_temp_store.search_notes("allenamento")
    assert len(lowercase_results) == 4


def test_search_is_case_insensitive(get_temp_store):
    uppercase_results = get_temp_store.search_notes("ALLENAMENTO")
    assert len(uppercase_results) == 4


def test_search_no_results(get_temp_store):
    results = get_temp_store.search_notes("non-existent-query")
    assert len(results) == 0 


def test_search_only_content(get_temp_store):
    only_content_results = get_temp_store.search_notes("squat")
    assert len(only_content_results) == 1


def test_delete_note(get_temp_store):
    get_temp_store.delete_note("spesa-settimana-1")

    with pytest.raises(NoteNotFoundError):
        get_temp_store.get_note("spesa-settimana-1")

def test_delete_note_not_found(get_temp_store):
    with pytest.raises(NoteNotFoundError):
        get_temp_store.delete_note("wrong-note-id")


def test_delete_tmp_only(get_temp_store):
    original_file = FIXTURE_PATH / "spesa-settimana-1.md"

    get_temp_store.delete_note("spesa-settimana-1")

    assert original_file.exists()

