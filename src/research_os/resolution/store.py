"""Append-only SQLite history for gap-resolution attempts."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading

from research_os.resolution.models import GapResolution


class ResolutionStore:
    """Persist each attempt once; a later attempt gets a new resolution_id."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock, self.connection:
            self.connection.execute("CREATE TABLE IF NOT EXISTS gap_resolutions (resolution_id TEXT PRIMARY KEY, gap_id TEXT NOT NULL, campaign_id TEXT, attempted_at TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL)")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_gap_resolutions_gap ON gap_resolutions(gap_id, attempted_at)")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_gap_resolutions_campaign ON gap_resolutions(campaign_id, attempted_at)")

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def save(self, resolution: GapResolution) -> GapResolution:
        if not resolution.valid:
            raise ValueError("cannot persist an invalid gap resolution digest")
        payload = json.dumps(resolution.to_dict(), ensure_ascii=False, sort_keys=True, default=str)
        with self._lock, self.connection:
            try:
                self.connection.execute("INSERT INTO gap_resolutions(resolution_id,gap_id,campaign_id,attempted_at,status,payload_json) VALUES(?,?,?,?,?,?)", (resolution.resolution_id, resolution.gap_id, resolution.campaign_id, resolution.attempted_at, resolution.status.value, payload))
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"resolution_id already exists; history is append-only: {resolution.resolution_id}") from exc
        return resolution

    def get(self, resolution_id: str) -> GapResolution:
        with self._lock:
            row = self.connection.execute("SELECT payload_json FROM gap_resolutions WHERE resolution_id=?", (resolution_id,)).fetchone()
        if row is None:
            raise KeyError(resolution_id)
        return _from_json(row["payload_json"])

    def list(self, *, campaign_id: str | None = None, gap_id: str | None = None, limit: int = 100) -> tuple[GapResolution, ...]:
        clauses, values = [], []
        if campaign_id is not None:
            clauses.append("campaign_id=?")
            values.append(campaign_id)
        if gap_id is not None:
            clauses.append("gap_id=?")
            values.append(gap_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._lock:
            rows = self.connection.execute(f"SELECT payload_json FROM gap_resolutions{where} ORDER BY attempted_at DESC LIMIT ?", (*values, int(limit))).fetchall()
        return tuple(_from_json(row["payload_json"]) for row in rows)


def _from_json(payload: str) -> GapResolution:
    data = json.loads(payload)
    data.pop("valid", None)
    return GapResolution(**data)
