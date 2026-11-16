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

    def list_note_ids(self) -> list[str]:
        """Return the ids of every note in the folder, sorted so the order is stable."""
        return sorted(file.stem for file in self.path.glob("*.md"))

    def get_note(self, note_id: str) -> Note:
        text = self._note_path(note_id).read_text(encoding="utf-8")

        # "", header, body. maxsplit=2 keeps any "---" inside the body intact.
        _, header, body = text.split("---", 2)

        fields = {}
        for row in header.strip().splitlines():
            key, value = row.split(": ", 1)
            fields[key] = value

        return Note(
            note_id=note_id,
            title=fields["title"],
            tags=fields["tags"].split(", "),
            content=body.strip(),
            date=fields["date"],
        )

    def search_notes(self, query: str) -> list[SearchResult]:
        """Find notes whose title, body or tags match the query, ignoring case."""
        query = query.lower()
        results = []
        for note_id in self.list_note_ids():
            note = self.get_note(note_id)
            # Title and body match on any substring. A tag is a whole label, so
            # the query has to equal it: "palestra" matches, "pales" doesn't.
            tags = [tag.lower() for tag in note.tags]
            if query in note.title.lower() or query in note.content.lower() or query in tags:
                results.append(SearchResult(note.note_id, note.title, sample=note.content[:100]))
        return results

    def delete_note(self, note_id: str) -> None:
        self._note_path(note_id).unlink()
