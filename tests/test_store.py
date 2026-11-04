import pytest
import shutil
from pathlib import Path
from store import NoteStore, NoteNotFoundError

fixtures_path = Path(__file__).parent.parent / "fixtures" / "base_notes"

@pytest.fixture
def get_temp_store(tmp_path):
    # Copy the contents of the fixtures directory to the temporary path
    shutil.copytree(fixtures_path, tmp_path / "notes", dirs_exist_ok=True)
    store = NoteStore(path=tmp_path / "notes")
    return store

def test_get_note_existing(get_temp_store):
    store = get_temp_store
    note = store.get_note("spesa-settimana-1")
    assert note.title == "Spesa settimana 1"


