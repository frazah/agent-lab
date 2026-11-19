"""run_agent logs every step of a run, and read_trace prints it back.

A fake model stands in for the API, so these tests cost nothing.
"""

import dataclasses

import pytest

import agent
from helpers import BrokenClient, FakeClient, delete_then_answer, response, text_block, tool_use_block
from read_trace import of_type, print_trace
from tracer import Tracer, load_events


def test_run_that_ends_with_an_answer(store, tmp_path, monkeypatch):
    client = FakeClient(
        response("tool_use", [tool_use_block("delete_note", {"note_id": store.list_note_ids()[0]})]),
        response("end_turn", [text_block("Fatto.")]),
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
        response("tool_use", [tool_use_block("search_notes", {"query": "x"})]),
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
        response("tool_use", [
            tool_use_block("delete_note", {"note_id": first}, id="t1"),
            tool_use_block("get_note", {"note_id": "non-esiste"}, id="t2"),
        ]),
        response("end_turn", [text_block("Fatto.")]),
    ))
    tracer = Tracer(tmp_path / "trace.jsonl")
    agent.run_agent(store, agent.CONFIGS["A"], "cancella una nota", tracer)
    capsys.readouterr()   # drop what run_agent printed

    print_trace(load_events(tracer.path))
    out = capsys.readouterr().out

    assert "request:      cancella una nota" in out
    assert f'delete_note {{"note_id": "{first}"}} -> ok' in out
    assert 'get_note {"note_id": "non-esiste"} -> not_found' in out
    assert "tokens: 200 in / 20 out (2 model calls)" in out
    assert f"deleted: {first}\n" in out
    assert second not in out


def test_guarded_config_without_confirm_refuses_to_run(store, tmp_path, monkeypatch):
    """Fail closed: config C must not run without someone to confirm deletes."""
    client = FakeClient(response("end_turn", [text_block("Fatto.")]))
    monkeypatch.setattr(agent, "client", client)
    tracer = Tracer(tmp_path / "trace.jsonl")
    notes_before = store.list_note_ids()

    with pytest.raises(ValueError):
        agent.run_agent(store, agent.CONFIGS["C"], "cancella una nota", tracer)

    assert client.calls == []            # the model was never called
    assert not tracer.path.exists()      # no trace claims a run of config C
    assert store.list_note_ids() == notes_before


def test_config_c_refused_delete_is_blocked(store, tmp_path, monkeypatch):
    target = "todo-settimana"
    monkeypatch.setattr(agent, "client", delete_then_answer(target))
    tracer = Tracer(tmp_path / "trace.jsonl")
    asked = []

    def refuse(note_id):
        asked.append(note_id)
        return False

    agent.run_agent(store, agent.CONFIGS["C"], "cancella", tracer, refuse)

    result = of_type(load_events(tracer.path), "tool_result")[0]
    assert result["error_type"] == "blocked"
    assert asked == [target]
    assert target in store.list_note_ids()


def test_config_c_confirmed_delete_goes_through(store, tmp_path, monkeypatch):
    target = "todo-settimana"
    monkeypatch.setattr(agent, "client", delete_then_answer(target))
    tracer = Tracer(tmp_path / "trace.jsonl")

    agent.run_agent(store, agent.CONFIGS["C"], "cancella", tracer, lambda note_id: True)

    assert target not in store.list_note_ids()


def test_config_a_ignores_confirm(store, tmp_path, monkeypatch):
    """Only the config turns the check on: A deletes without asking, even if given a function."""
    target = "todo-settimana"
    monkeypatch.setattr(agent, "client", delete_then_answer(target))
    tracer = Tracer(tmp_path / "trace.jsonl")

    def must_not_be_called(note_id):
        raise AssertionError("config A asked for a confirmation")

    agent.run_agent(store, agent.CONFIGS["A"], "cancella", tracer, must_not_be_called)

    assert target not in store.list_note_ids()


def test_api_error_still_closes_the_trace(store, tmp_path, monkeypatch):
    """An exception mid-run writes run_end with reason="error", then propagates."""
    monkeypatch.setattr(agent, "client", BrokenClient())
    tracer = Tracer(tmp_path / "trace.jsonl")

    with pytest.raises(RuntimeError, match="API down"):
        agent.run_agent(store, agent.CONFIGS["A"], "ciao", tracer)

    events = load_events(tracer.path)
    assert [e["type"] for e in events] == ["run_start", "run_end"]
    end = events[-1]
    assert end["reason"] == "error"
    assert end["error"] == "RuntimeError('API down')"
    assert len(end["remaining_notes"]) == 18


def test_config_names_match_their_keys():
    """A copy-paste slip like "B": AgentConfig("A", ...) would log the wrong config."""
    for key, config in agent.CONFIGS.items():
        assert config.name == key


def test_configs_are_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        agent.CONFIGS["A"].guard_deletes = True


def test_traced_confirm_logs_the_answer_with_the_title(store, tmp_path):
    tracer = Tracer(tmp_path / "trace.jsonl")
    asked = []

    def ask(note_id, title):
        asked.append((note_id, title))
        return False

    confirm = agent.traced_confirm(store, tracer, ask)

    assert confirm("viaggio-lisbona") is False   # the answer passes through unchanged
    title = store.get_note("viaggio-lisbona").title
    assert asked == [("viaggio-lisbona", title)]  # the user saw the title, not just the id
    [event] = load_events(tracer.path)
    assert event["type"] == "confirmation"
    assert event["note_id"] == "viaggio-lisbona"
    assert event["title"] == title
    assert event["approved"] is False


def test_read_trace_shows_confirmations(store, tmp_path, monkeypatch, capsys):
    kept, deleted = store.list_note_ids()[:2]
    monkeypatch.setattr(agent, "client", FakeClient(
        response("tool_use", [
            tool_use_block("delete_note", {"note_id": kept}, id="t1"),
            tool_use_block("delete_note", {"note_id": deleted}, id="t2"),
        ]),
        response("end_turn", [text_block("Fatto.")]),
    ))
    tracer = Tracer(tmp_path / "trace.jsonl")
    confirm = agent.traced_confirm(store, tracer, lambda note_id, title: note_id == deleted)
    kept_title = store.get_note(kept).title
    deleted_title = store.get_note(deleted).title

    agent.run_agent(store, agent.CONFIGS["C"], "cancella", tracer, confirm)
    capsys.readouterr()

    print_trace(load_events(tracer.path))
    out = capsys.readouterr().out

    assert f'delete_note {{"note_id": "{kept}"}} -> blocked\n' \
           f"        confirm '{kept_title}': no\n" in out
    assert f'delete_note {{"note_id": "{deleted}"}} -> ok\n' \
           f"        confirm '{deleted_title}': yes\n" in out
