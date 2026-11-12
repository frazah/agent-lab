"""Read, search and delete Markdown notes stored in a folder.

Each note is a file named <note_id>.md, with a small header on top:

    ---
    title: Spesa settimana 1
    tags: spesa, casa
    date: 2026-10-05
    ---
    Note body...
"""

from dataclasses import dataclass
from pathlib import Path

class NoteStoreError(Exception):
    """Base class for the errors the store expects. Catch this to catch them all."""
    pass

class NoteNotFoundError(NoteStoreError):
    def __init__(self, note_id: str):
        self.note_id = note_id
        super().__init__(f"Note not found: {note_id}")

class InvalidNoteIdError(NoteStoreError):
    def __init__(self, note_id: str):
        self.note_id = note_id
        super().__init__(f"Invalid note ID: {note_id}")

@dataclass
class Note:
    note_id: str
    title: str
    tags: list[str]
    content: str
    date: str

@dataclass
class SearchResult:
    note_id: str
    title: str
    sample: str

@dataclass
class NoteStore:
    path: Path

    def _note_path(self, note_id: str) -> Path:
        folder = self.path.resolve()
        file = (self.path / f"{note_id}.md").resolve()

        # Block ids like "../secret" that would reach files outside the folder.
        if not file.is_relative_to(folder):
            raise InvalidNoteIdError(note_id)

        if not file.exists():
            raise NoteNotFoundError(note_id)

        return file

    def delete_note(self, note_id:str)-> None:
        self._note_path(note_id=note_id).unlink()

    def get_note(self, note_id: str)-> Note:
        note = self._note_path(note_id=note_id).read_text()

        # parts[1] is the header, parts[2] the body.
        parts = note.split("---")
        frontmatter = parts[1].strip()
        rows = frontmatter.splitlines()
        data = {}

        for row in rows:
            key, value = row.split(": ", 1)
            data[key] = value

        content = parts[2].strip()    
        tags = data["tags"].split(", ")

        note_obj= Note(note_id=note_id, title=data["title"], tags=tags, content=content, date=data["date"])
        return note_obj

    def search_notes(self, query: str)-> list[SearchResult]:
        """Find notes whose title, body or tags match the query, ignoring case."""
        results = []
        for file in sorted(self.path.glob("*.md")):  # sorted, so results come in a stable order
            note = self.get_note(file.stem)
            query_lower = query.lower()
            # Title and body match on any substring. A tag is a whole label, so
            # the query has to equal it: "palestra" matches, "pales" doesn't.
            tags_lower = [tag.lower() for tag in note.tags]
            if (
                query_lower in note.title.lower()
                or query_lower in note.content.lower()
                or query_lower in tags_lower
            ):
                results.append(SearchResult(note_id=note.note_id, title=note.title, sample=note.content[:100]))
        return results


if __name__ == "__main__":
    store = NoteStore(Path("fixtures/base_notes"))
   
    search_res = store.search_notes("allenamento")
    print(f"Found {len(search_res)} results for 'allenamento':")
    for result in search_res:
        print(result.note_id,result.title, result.sample)
        print("----")


