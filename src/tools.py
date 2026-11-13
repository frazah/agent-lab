"""The tools the model can call, and the dispatcher that runs them.

Each tool has a name, a description and a JSON Schema for its arguments.
The description is all the model knows about a tool, so it says what the tool
does, what it returns and how it can fail.

The descriptions are part of the experiment: changing them changes the agent's
behavior, so record any edit in experiments.md.
"""

import json
from dataclasses import asdict

from anthropic.types import ToolParam

from store import NoteStore, NoteStoreError

SEARCH_NOTES: ToolParam = {
    "name": "search_notes",
    "description": (
        "Search the user's personal notes by keyword. Use this first whenever you "
        "need a note but don't know its note_id, or to find out which notes talk "
        "about a topic. The match is a case-insensitive substring match of the whole "
        "query against each note's title and body: it is not fuzzy and does not split "
        "the query into words, so 'palestra scheda' only matches notes containing that "
        "exact phrase. Prefer a single distinctive keyword, and retry with a synonym or "
        "a shorter word if nothing comes back. A note also matches when the query is "
        "exactly one of its tags (ignoring case), e.g. 'palestra' or 'ricette'; a partial "
        "tag like 'ricett' does not match the tag. The notes are "
        "written in Italian, so search in Italian (e.g. 'ricetta', not 'recipe'). "
        "Returns a list of matches, each with note_id, title and only the first ~100 "
        "characters of the body: to read a note in full, call get_note with its note_id. "
        "An empty list means no note matched."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keyword or exact phrase to look for, e.g. 'allenamento' or 'lisbona'.",
            }
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}

GET_NOTE: ToolParam = {
    "name": "get_note",
    "description": (
        "Read one note in full, given its note_id. Use this after search_notes, when "
        "you need the actual content of a note to answer the user. Returns the note's "
        "title, tags, date (YYYY-MM-DD) and full body text. The note_id is the "
        "identifier returned by search_notes, a lowercase slug like "
        "'ricetta-pasta-alla-norma': do not guess it from the title and do not add a "
        "'.md' extension or a folder path. Fails with a 'not found' error if no note "
        "has that id, and with an 'invalid id' error if the id points outside the "
        "notes folder."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "note_id": {
                "type": "string",
                "description": "The note's id as returned by search_notes, e.g. 'viaggio-lisbona'.",
            }
        },
        "required": ["note_id"],
        "additionalProperties": False,
    },
}

DELETE_NOTE: ToolParam = {
    "name": "delete_note",
    "description": (
        "Permanently delete one note, given its note_id. This cannot be undone: there "
        "is no trash and no backup. The note_id is the identifier returned by "
        "search_notes. Returns a confirmation on success. Fails with a 'not found' error if "
        "no note has that id, and with an 'invalid id' error if the id points outside "
        "the notes folder."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "note_id": {
                "type": "string",
                "description": "The id of the note to delete, as returned by search_notes.",
            }
        },
        "required": ["note_id"],
        "additionalProperties": False,
    },
}

TOOLS: list[ToolParam] = [SEARCH_NOTES, GET_NOTE, DELETE_NOTE]


def _to_json(obj) -> str:
    # Keep accented letters readable: the model sees "è", not the escape \u00e8.
    return json.dumps(obj, ensure_ascii=False, indent=2)


def dispatch(store: NoteStore, name: str, args: dict) -> str:
    """Run a tool and return its result as text, since the model only reads text.

    Expected problems (a missing note, a bad id, an unknown tool, a missing
    argument) come back as a message starting with "Error:", so the model can
    fix its call. Anything else is a bug in our code, so we let it crash.
    """
    # The one argument each tool needs.
    required = {"search_notes": "query", "get_note": "note_id", "delete_note": "note_id"}
    if name not in required:
        return f"Error: unknown tool '{name}'. Available tools: {', '.join(required)}"
    
    # Check the argument here rather than catching KeyError below: the store can
    # raise KeyError on its own, and we'd report it as a missing argument.
    arg = required[name]
    if arg not in args:
        return f"Error: missing required argument '{arg}' for tool '{name}'"
    
    value = args[arg]

    try:
        # Notes and search results are dataclasses: asdict + JSON turns them into text.
        if name == "search_notes":
            return _to_json([asdict(r) for r in store.search_notes(value)])
        if name == "get_note":
            return _to_json(asdict(store.get_note(value)))
        store.delete_note(value)
        return f"Note deleted: {value}"
    except NoteStoreError as e:
        # Covers both NoteNotFoundError and InvalidNoteIdError.
        return f"Error: {e}"
