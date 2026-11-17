"""Print a trace written by agent.py in a readable form.
Usage: python src/read_trace.py [logs/trace-....jsonl]
With no path, it opens the most recent trace in logs/.
"""

import json
import sys
from pathlib import Path
from typing import Optional

from store import NoteStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS = PROJECT_ROOT / "logs"

BASE_NOTES = PROJECT_ROOT / "fixtures" / "base_notes"


def load_events(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def latest_trace() -> Path:
    traces = list(LOGS.glob("trace-*.jsonl"))
    if not traces:
        sys.exit(f"No traces in {LOGS}")
    return max(traces)


def of_type(events: list[dict], event_type: str) -> list[dict]:
    return [e for e in events if e["type"] == event_type]


def print_run(start: Optional[dict]) -> None:
    print("== Run")
    if start is None:
        print("(no run_start)")
        return
    print(f"request:      {start['request']}")
    print(f"code_version: {start['code_version']}")
    print(f"config:       {start['config']}")
    print(f"model:        {start['model']}")


def outcome(result: Optional[dict]) -> str:
    if result is None:
        return "no result"  # the run stopped between the call and the result
    if not result["is_error"]:
        return "ok"
    # Traces written before error_type existed only have is_error.
    return result.get("error_type") or "error"


def confirmations_by_call(events: list[dict]) -> dict[str, dict]:
    """Match each confirmation event to its tool_call.
    A confirmation has no tool_use_id: the confirm function doesn't know it.
    But it is logged while its delete_note runs, so it always comes right
    after that call's tool_call event.
    """
    matched = {}
    last_call_id = None
    for event in events:
        if event["type"] == "tool_call":
            last_call_id = event["tool_use_id"]
        elif event["type"] == "confirmation" and last_call_id is not None:
            matched[last_call_id] = event
    return matched


def print_steps(events: list[dict]) -> None:
    print("\n== Steps")
    responses = of_type(events, "model_response")
    calls = of_type(events, "tool_call")
    results = {e["tool_use_id"]: e for e in of_type(events, "tool_result")}
    confirmations = confirmations_by_call(events)

    if not responses:
        print("(no model_response events: trace written before they were logged)")

    for response in responses:
        step = response["step"]
        step_calls = [c for c in calls if c["step"] == step]
        if not step_calls:
            print(f"[{step}] {response['stop_reason']}: no tools")
            continue
        print(f"[{step}]")
        for call in step_calls:
            args = json.dumps(call["args"], ensure_ascii=False)
            print(f"    {call['name']} {args} -> {outcome(results.get(call['tool_use_id']))}")
            confirmation = confirmations.get(call["tool_use_id"])
            if confirmation is not None:
                answer = "yes" if confirmation["approved"] else "no"
                print(f"        confirm '{confirmation['title']}': {answer}")


def print_cost(events: list[dict]) -> None:
    print("\n== Cost")
    responses = of_type(events, "model_response")
    if not responses:
        print("(no model_response events)")
        return
    tokens_in = sum(r["input_tokens"] for r in responses)
    tokens_out = sum(r["output_tokens"] for r in responses)
    print(f"tokens: {tokens_in} in / {tokens_out} out ({len(responses)} model calls)")


def print_end(end: Optional[dict]) -> None:
    print("\n== End")
    if end is None:
        print("(no run_end: the run crashed or is still running)")
        return
    deleted = sorted(set(NoteStore(BASE_NOTES).list_note_ids()) - set(end["remaining_notes"]))
    print(f"reason:  {end['reason']}")
    if end.get("error"):
        print(f"error:   {end['error']}")
    print(f"steps:   {end['steps']}")
    print(f"deleted: {', '.join(deleted) if deleted else 'none'}")


def print_trace(events: list[dict]) -> None:
    starts = of_type(events, "run_start")
    ends = of_type(events, "run_end")
    print_run(starts[0] if starts else None)
    print_steps(events)
    print_cost(events)
    print_end(ends[0] if ends else None)


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_trace()
    if not path.is_file():
        sys.exit(f"Trace not found: {path}")
    print(f"trace: {path}\n")
    print_trace(load_events(path))
