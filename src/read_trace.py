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
# The notes every run starts from (reset.sh copies them): deleted = these - remaining.
BASE_NOTES = PROJECT_ROOT / "fixtures" / "base_notes"


def load_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def latest_trace() -> Path:
    traces = list(LOGS.glob("trace-*.jsonl"))
    if not traces:
        sys.exit(f"No traces in {LOGS}")
    # The names hold date and time, so alphabetical order is chronological order.
    return max(traces)


def outcome(result: Optional[dict]) -> str:
    if result is None:
        return "no result"  # the run stopped between the call and the result
    if not result["is_error"]:
        return "ok"
    # Traces written before error_type existed only have is_error.
    return result.get("error_type") or "error"


def print_trace(events: list[dict]) -> None:
    start = next((e for e in events if e["type"] == "run_start"), None)
    end = next((e for e in events if e["type"] == "run_end"), None)
    responses = [e for e in events if e["type"] == "model_response"]
    calls = [e for e in events if e["type"] == "tool_call"]
    results = {e["tool_use_id"]: e for e in events if e["type"] == "tool_result"}

    print("== Run")
    if start:
        print(f"request:      {start['request']}")
        print(f"code_version: {start['code_version']}")
        print(f"config:       {start['config']}")
        print(f"model:        {start['model']}")
    else:
        print("(no run_start)")

    print("\n== Steps")
    if not responses and not calls:
        print("(no model_response / tool_call events: trace written before they were logged)")
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

    print("\n== Cost")
    if responses:
        tokens_in = sum(r["input_tokens"] for r in responses)
        tokens_out = sum(r["output_tokens"] for r in responses)
        print(f"tokens: {tokens_in} in / {tokens_out} out ({len(responses)} model calls)")
    else:
        print("(no model_response events)")

    print("\n== End")
    if end is None:
        print("(no run_end: the run crashed or is still running)")
        return
    deleted = sorted(set(NoteStore(BASE_NOTES).list_note_ids()) - set(end["remaining_notes"]))
    print(f"reason:  {end['reason']}")
    print(f"steps:   {end['steps']}")
    print(f"deleted: {', '.join(deleted) if deleted else 'none'}")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_trace()
    if not path.is_file():
        sys.exit(f"Trace not found: {path}")
    print(f"trace: {path}\n")
    print_trace(load_events(path))
