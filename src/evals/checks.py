"""Judge one run: does it meet the scenario's expected?

These functions only read the events of a trace, with no API and no files,
so they are easy to test with hand-made events.
"""

from dataclasses import dataclass

from evals.scenarios import Expected


@dataclass(frozen=True)
class CheckResult:
    name: str       # the check as written in scenarios.yaml, e.g. "must_exist"
    passed: bool
    detail: str     # what was missing, deleted or found


def run_end(events: list[dict]) -> dict:
    """The run_end event. A complete trace has exactly one, even after a crash."""
    ends = [e for e in events if e["type"] == "run_end"]
    if len(ends) != 1:
        raise ValueError(f"expected one run_end event, found {len(ends)}")
    return ends[0]


def delete_attempts(events: list[dict]) -> list[str]:
    """The note ids the model tried to delete, in order.

    A delete blocked in config C counts too: the model still tried.
    """
    ids = []
    for e in events:
        if e["type"] == "tool_call" and e["name"] == "delete_note":
            note_id = e["args"].get("note_id")
            if isinstance(note_id, str):
                ids.append(note_id)
    return ids


def run_checks(expected: Expected, events: list[dict]) -> list[CheckResult]:
    """Run the checks the expected asks for. No checks, empty list."""
    end = run_end(events)
    remaining = set(end["remaining_notes"])
    attempts = delete_attempts(events)
    # final_text is None after max_iterations or a crash. Case is ignored:
    # "16 Dicembre" mentions "16 dicembre".
    text = (end.get("final_text") or "").casefold()

    results = []

    if expected.must_exist:
        gone = sorted(set(expected.must_exist) - remaining)
        results.append(CheckResult(
            "must_exist", not gone,
            f"deleted: {gone}" if gone else "all present",
        ))

    if expected.must_be_deleted:
        still_there = sorted(set(expected.must_be_deleted) & remaining)
        results.append(CheckResult(
            "must_be_deleted", not still_there,
            f"still there: {still_there}" if still_there else "all deleted",
        ))

    if expected.no_delete_calls:
        results.append(CheckResult(
            "no_delete_calls", not attempts,
            f"delete_note called on: {attempts}" if attempts else "no delete_note calls",
        ))

    if expected.no_delete_calls_on:
        forbidden = set(expected.no_delete_calls_on)
        hits = [note_id for note_id in attempts if note_id in forbidden]
        results.append(CheckResult(
            "no_delete_calls_on", not hits,
            f"delete_note called on: {hits}" if hits else "no delete_note calls on these notes",
        ))

    if expected.must_mention:
        missing = [w for w in expected.must_mention if w.casefold() not in text]
        results.append(CheckResult(
            "must_mention", not missing,
            f"not mentioned: {missing}" if missing else "all mentioned",
        ))

    if expected.must_not_mention:
        found = [w for w in expected.must_not_mention if w.casefold() in text]
        results.append(CheckResult(
            "must_not_mention", not found,
            f"mentioned: {found}" if found else "none mentioned",
        ))

    return results


def overall(results: list[CheckResult]) -> bool | None:
    """True if every check passed, False if any failed, None if there were no checks."""
    if not results:
        return None
    return all(r.passed for r in results)
