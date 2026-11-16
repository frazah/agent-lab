"""run_agent writes a run_start and a run_end line to the trace, without calling the API."""

import json
from types import SimpleNamespace

import agent
from tracer import Tracer


def _response(stop_reason, content):
    usage = SimpleNamespace(input_tokens=0, output_tokens=0)
    return SimpleNamespace(stop_reason=stop_reason, content=content, usage=usage)


def _text(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use(name, tool_input, id="t1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=id)


class FakeClient:
    """Returns the queued responses one per call; repeats the last one forever."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.messages = self

    def create(self, **kwargs):
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def _read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_end_turn_writes_start_and_end(store, tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "client", FakeClient(
        _response("tool_use", [_tool_use("delete_note", {"note_id": store.list_note_ids()[0]})]),
        _response("end_turn", [_text("Fatto.")]),
    ))
    tracer = Tracer(tmp_path / "trace.jsonl")
    deleted = store.list_note_ids()[0]

    agent.run_agent(store, "cancella una nota", tracer)

    events = _read(tracer.path)
    assert [e["type"] for e in events] == [
        "run_start",
        "model_response", "tool_call", "tool_result",
        "model_response",
        "run_end",
    ]
    start, resp1, call, result, resp2, end = events

    assert resp1["step"] == 1
    assert resp1["stop_reason"] == "tool_use"
    assert resp1["text"] is None
    assert resp2["step"] == 2
    assert resp2["text"] == "Fatto."

    assert call["step"] == result["step"] == 1
    assert call["tool_use_id"] == result["tool_use_id"] == "t1"
    assert call["name"] == result["name"] == "delete_note"
    assert call["args"] == {"note_id": deleted}
    assert result["is_error"] is False
    assert result["error_type"] is None

    assert start["type"] == "run_start"
    assert start["request"] == "cancella una nota"
    assert start["model"] == agent.MODEL
    assert start["system_prompt"] == agent.SYSTEM
    assert start["code_version"] == agent.CODE_VERSION
    assert start["config"] == "A"

    assert end["type"] == "run_end"
    assert end["reason"] == "end_turn"
    assert end["steps"] == 2
    assert end["final_text"] == "Fatto."
    assert deleted not in end["remaining_notes"]
    assert end["remaining_notes"] == sorted(end["remaining_notes"])
    assert start["run_id"] == end["run_id"]


def test_max_iterations_is_recorded(store, tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "client", FakeClient(
        _response("tool_use", [_tool_use("search_notes", {"query": "x"})]),
    ))
    tracer = Tracer(tmp_path / "trace.jsonl")

    agent.run_agent(store, "loop", tracer)

    events = _read(tracer.path)
    start, end = events[0], events[-1]
    # Each of the N steps writes model_response + tool_call + tool_result.
    assert len(events) == 2 + 3 * agent.MAX_ITERATIONS
    assert end["reason"] == "max_iterations"
    assert end["steps"] == agent.MAX_ITERATIONS
    assert end["final_text"] is None
    assert len(end["remaining_notes"]) == 18
