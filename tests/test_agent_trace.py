"""run_agent traces every step of a run, and read_trace prints it back.

A fake client stands in for the API, so these tests cost nothing.
"""

from types import SimpleNamespace

import pytest

import agent
from read_trace import load_events, print_trace
from tracer import Tracer


def _response(stop_reason, content):
    usage = SimpleNamespace(input_tokens=100, output_tokens=10)
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
        self.calls = []  # the kwargs of every create() call, to check what the agent sent

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def test_run_that_ends_with_an_answer(store, tmp_path, monkeypatch):
    client = FakeClient(
        _response("tool_use", [_tool_use("delete_note", {"note_id": store.list_note_ids()[0]})]),
        _response("end_turn", [_text("Fatto.")]),
    )
    monkeypatch.setattr(agent, "client", client)
    tracer = Tracer(tmp_path / "trace.jsonl")
    deleted = store.list_note_ids()[0]
    config = agent.CONFIGS["B"]  # not A, so the test can tell the config was really used

    agent.run_agent(store, config, "cancella una nota", tracer)

    events = load_events(tracer.path)
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
    assert start["system_prompt"] == config.system_prompt
    assert start["code_version"] == agent.CODE_VERSION
    assert start["config"] == "B"
    assert all(call["system"] == config.system_prompt for call in client.calls)

    assert end["type"] == "run_end"
    assert end["reason"] == "end_turn"
    assert end["steps"] == 2
    assert end["final_text"] == "Fatto."
    assert deleted not in end["remaining_notes"]
    assert end["remaining_notes"] == sorted(end["remaining_notes"])
    assert start["run_id"] == end["run_id"]


def test_run_that_hits_max_iterations(store, tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "client", FakeClient(
        _response("tool_use", [_tool_use("search_notes", {"query": "x"})]),
    ))
    tracer = Tracer(tmp_path / "trace.jsonl")

    agent.run_agent(store, agent.CONFIGS["A"], "loop", tracer)

    events = load_events(tracer.path)
    start, end = events[0], events[-1]
    # Each of the N steps writes model_response + tool_call + tool_result.
    assert len(events) == 2 + 3 * agent.MAX_ITERATIONS
    assert end["reason"] == "max_iterations"
    assert end["steps"] == agent.MAX_ITERATIONS
    assert end["final_text"] is None
    assert len(end["remaining_notes"]) == 18


def test_read_trace_prints_the_run(store, tmp_path, monkeypatch, capsys):
    first, second = store.list_note_ids()[:2]
    monkeypatch.setattr(agent, "client", FakeClient(
        _response("tool_use", [
            _tool_use("delete_note", {"note_id": first}, id="t1"),
            _tool_use("get_note", {"note_id": "non-esiste"}, id="t2"),
        ]),
        _response("end_turn", [_text("Fatto.")]),
    ))
    tracer = Tracer(tmp_path / "trace.jsonl")
    agent.run_agent(store, agent.CONFIGS["A"], "cancella una nota", tracer)
    capsys.readouterr()  # drop what run_agent printed

    print_trace(load_events(tracer.path))
    out = capsys.readouterr().out

    assert "request:      cancella una nota" in out
    assert f'delete_note {{"note_id": "{first}"}} -> ok' in out
    assert 'get_note {"note_id": "non-esiste"} -> not_found' in out
    assert "tokens: 200 in / 20 out (2 model calls)" in out
    assert f"deleted: {first}\n" in out
    assert second not in out


def test_config_with_missing_delete_check_refuses_to_run(store, tmp_path, monkeypatch):
    """Fail closed: config C must not run until its delete check exists."""
    client = FakeClient(_response("end_turn", [_text("Fatto.")]))
    monkeypatch.setattr(agent, "client", client)
    tracer = Tracer(tmp_path / "trace.jsonl")
    notes_before = store.list_note_ids()

    with pytest.raises(NotImplementedError):
        agent.run_agent(store, agent.CONFIGS["C"], "cancella una nota", tracer)

    assert client.calls == []            # the model was never called
    assert not tracer.path.exists()      # no trace claims a run of config C
    assert store.list_note_ids() == notes_before
