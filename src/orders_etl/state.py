"""Watermark persistence for incremental runs."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class WatermarkStore:
    """Stores the latest business timestamp successfully loaded, as JSON."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def get(self) -> datetime | None:
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return datetime.fromisoformat(data["watermark"]) if data.get("watermark") else None

    def set(self, ts: datetime, rows: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "watermark": ts.isoformat(sep=" "),
            "rows_loaded": rows,
            "updated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
