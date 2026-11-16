import json
from tracer import Tracer

def test_log_writes_one_json_line_per_event(tmp_path):
    tracer = Tracer(tmp_path / "trace.jsonl")

    tracer.log("event1", field1="value1")
    tracer.log("event2", field2="value2")

    with open(tmp_path / "trace.jsonl", "r") as f:
        lines = f.readlines()

    assert len(lines) == 2

    event1 = json.loads(lines[0])
    assert event1["type"] == "event1"
    assert event1["field1"] == "value1"

    event2 = json.loads(lines[1])
    assert event2["type"] == "event2"
    assert event2["field2"] == "value2"
