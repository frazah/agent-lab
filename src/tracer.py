"""Write what happens during a run to a JSONL file, one JSON event per line.

Each event is appended and the file is closed right away, so if the agent
crashes, everything logged until then is already on disk.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path


class Tracer:
    def __init__(self, path: Path):
        self.path = path
        self.run_id = uuid.uuid4().hex

    def log(self, event_type: str, **data) -> None:
        event = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            "run_id": self.run_id,
            **data,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_events(path: Path) -> list[dict]:
    """Read back the events of a trace file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]
