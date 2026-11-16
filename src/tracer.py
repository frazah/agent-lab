import datetime
import json
from pathlib import Path
import uuid


class Tracer:
    def __init__(self, path: Path):
        self.path = path
        self.run_id = uuid.uuid4().hex

    def log(self, event_type: str, **data) -> None:
        event = {
            "type": event_type,
            "timestamp": datetime.datetime.now().isoformat(),
            "run_id": self.run_id,
            **data
        }

        json_event = json.dumps(event, ensure_ascii=False)

        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json_event + "\n")