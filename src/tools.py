"""The tools the model can call, and the dispatcher that runs them.

Each tool has a name, a description and a JSON Schema for its arguments.
The description is all the model knows about a tool, so it says what the tool
does, what it returns and how it can fail.

The arguments of each tool are a Pydantic model. The schema sent to the model
is generated from it, and dispatch validates the arguments with the same model,
so the rules the model reads are the rules the code checks.

The descriptions are part of the experiment: changing them changes the agent's
behavior, so record any edit in experiments.md.
"""

import json
from dataclasses import asdict
from typing import Annotated

from anthropic.types import ToolParam
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from store import NoteStore, NoteStoreError

ID_PATTERN = r"^[a-z0-9-]+$"
MAX_ID_LENGTH = 100
MAX_QUERY_LENGTH = 1000

# A str with the id rules attached, shared by get_note and delete_note.
NoteId = Annotated[
    str,
    Field(
        pattern=ID_PATTERN,
        min_length=1,
        max_length=MAX_ID_LENGTH,
        description="The note's id as returned by search_notes, e.g. 'viaggio-lisbona'.",
    ),
]


class SearchNotesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(
        min_length=1,
        max_length=MAX_QUERY_LENGTH,
        description="Keyword or exact phrase to look for, e.g. 'allenamento' or 'lisbona'.",
    )


class GetNoteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note_id: NoteId


class DeleteNoteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note_id: NoteId


DESCRIPTIONS: dict[str, str] = {
    "search_notes": (
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
    "get_note": (
        "Read one note in full, given its note_id. Use this after search_notes, when "
        "you need the actual content of a note to answer the user. Returns the note's "
        "title, tags, date (YYYY-MM-DD) and full body text. The note_id is the "
        "identifier returned by search_notes, a lowercase slug like "
        "'ricetta-pasta-alla-norma': do not guess it from the title and do not add a "
        "'.md' extension or a folder path. Fails with a 'not found' error if no note "
        "has that id, and with an 'invalid id' error if the id points outside the "
        "notes folder."
    ),
    "delete_note": (
        "Permanently delete one note, given its note_id. This cannot be undone: there "
        "is no trash and no backup. The note_id is the identifier returned by "
        "search_notes. Returns a confirmation on success. Fails with a 'not found' error if "
        "no note has that id, and with an 'invalid id' error if the id points outside "
        "the notes folder."
    ),
}

# Which Pydantic model checks the arguments of each tool.
ARGS_MODELS: dict[str, type[BaseModel]] = {
    "search_notes": SearchNotesArgs,
    "get_note": GetNoteArgs,
    "delete_note": DeleteNoteArgs,
}

# The tool definitions sent to the API, with the schema generated from the models.
TOOLS: list[ToolParam] = [
    {
        "name": name,
        "description": DESCRIPTIONS[name],
        "input_schema": model.model_json_schema(),
    }
    for name, model in ARGS_MODELS.items()
]


def _to_json(obj) -> str:
    # Keep accented letters readable: the model sees "è", not the escape \u00e8.
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _format_validation_error(name: str, e: ValidationError) -> str:
    # Only the field and the reason: str(e) also has links to Pydantic's docs,
    # which are noise for the model.
    problems = []
    for err in e.errors():
        # loc is empty when the input as a whole is wrong (e.g. not a dict).
        field = ".".join(str(part) for part in err["loc"]) or "arguments"
        problems.append(f"'{field}': {err['msg']}")
    return f"Error: invalid arguments for tool '{name}': " + "; ".join(problems)


def dispatch(store: NoteStore, name: str, raw_args: dict) -> str:
    """Run a tool and return its result as text, since the model only reads text.

    Expected problems (a missing note, a bad id, an unknown tool, invalid
    arguments) come back as a message starting with "Error:", so the model can
    fix its call. Anything else is a bug in our code, so we let it crash.
    """
    if name not in ARGS_MODELS:
        return f"Error: unknown tool '{name}'. Available tools: {', '.join(ARGS_MODELS)}"

    # Each branch validates with its own class, so the type checker knows
    # which fields `args` has. The store still checks ids on its own.
    try:
        if name == "search_notes":
            args = SearchNotesArgs.model_validate(raw_args)
            return _to_json([asdict(r) for r in store.search_notes(args.query)])
        if name == "get_note":
            args = GetNoteArgs.model_validate(raw_args)
            return _to_json(asdict(store.get_note(args.note_id)))
        if name == "delete_note":
            args = DeleteNoteArgs.model_validate(raw_args)
            store.delete_note(args.note_id)
            return f"Note deleted: {args.note_id}"
    except ValidationError as e:
        return _format_validation_error(name, e)
    except NoteStoreError as e:
        # Covers both NoteNotFoundError and InvalidNoteIdError.
        return f"Error: {e}"

    # In ARGS_MODELS but without a branch above: a bug in our code.
    raise AssertionError(f"no handler for tool '{name}'")
