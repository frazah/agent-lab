from dataclasses import dataclass
from pathlib import Path

class NoteStoreError(Exception):
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

        if not file.is_relative_to(folder):
            raise InvalidNoteIdError(note_id)

        if not file.exists():
            raise NoteNotFoundError(note_id)

        return file

    def delete_note(self, note_id:str)-> None:
        self._note_path(note_id=note_id).unlink()

    def get_note(self, note_id: str)-> Note:
        note = self._note_path(note_id=note_id).read_text()
        
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
        results = []
        for file in self.path.glob("*.md"):
            note = self.get_note(file.stem)
            query_lower = query.lower()
            if query_lower in note.title.lower() or query_lower in note.content.lower():
                results.append(SearchResult(note_id=note.note_id, title=note.title, sample=note.content[:20]))
        return results


if __name__ == "__main__":
    store = NoteStore(Path("fixtures/base_notes"))
   
    search_res = store.search_notes("allenamento")
    print(f"Found {len(search_res)} results for 'allenamento':")
    for result in search_res:
        print(result.note_id,result.title, result.sample)
        print("----")


