import json
from datetime import datetime, timezone
from pathlib import Path

class AuditLogger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
    def record(self, event_type: str, payload: dict) -> None:
        row = {"recorded_at": datetime.now(timezone.utc).isoformat(), "event_type": event_type, "payload": payload}
        with self.path.open("a", encoding="utf-8") as f: f.write(json.dumps(row, sort_keys=True, default=str) + "\n")
