import json

from tracer import Tracer, load_events


def test_log_writes_one_json_line_per_event(tmp_path):
    tracer = Tracer(tmp_path / "trace.jsonl")

    tracer.log("event1", field1="value1")
    tracer.log("event2", field2="value2")

    lines = tracer.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first, second = (json.loads(line) for line in lines)
    assert first["type"] == "event1"
    assert first["field1"] == "value1"
    assert second["type"] == "event2"
    assert second["field2"] == "value2"
    assert first["run_id"] == second["run_id"]

    assert load_events(tracer.path) == [first, second]
