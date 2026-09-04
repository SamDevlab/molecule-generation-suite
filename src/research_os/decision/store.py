"""Append-only SQLite storage for scientific decisions."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading

from research_os.decision.models import ScientificDecision


class DecisionStore:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock, self.connection:
            self.connection.execute("CREATE TABLE IF NOT EXISTS scientific_decisions (decision_id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, created_at TEXT NOT NULL, digest TEXT NOT NULL, payload_json TEXT NOT NULL)")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_scientific_decisions_created ON scientific_decisions(created_at DESC)")

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def save(self, decision: ScientificDecision) -> ScientificDecision:
        payload = json.dumps(decision.to_dict(), ensure_ascii=False, sort_keys=True)
        with self._lock, self.connection:
            existing = self.connection.execute("SELECT digest FROM scientific_decisions WHERE decision_id=?", (decision.decision_id,)).fetchone()
            if existing is not None:
                if existing["digest"] != decision.digest:
                    raise ValueError(f"decision_id already exists with a different digest: {decision.decision_id}")
                return decision
            self.connection.execute("INSERT INTO scientific_decisions(decision_id,campaign_id,created_at,digest,payload_json) VALUES(?,?,?,?,?)", (decision.decision_id, decision.campaign_id, decision.created_at, decision.digest, payload))
        return decision

    def get(self, decision_id: str) -> ScientificDecision:
        with self._lock:
            row = self.connection.execute("SELECT payload_json FROM scientific_decisions WHERE decision_id=?", (decision_id,)).fetchone()
        if row is None:
            raise KeyError(decision_id)
        return ScientificDecision.from_dict(json.loads(row["payload_json"]))

    def list(self, *, campaign_id: str | None = None, limit: int = 100) -> tuple[ScientificDecision, ...]:
        with self._lock:
            if campaign_id:
                rows = self.connection.execute("SELECT payload_json FROM scientific_decisions WHERE campaign_id=? ORDER BY created_at DESC LIMIT ?", (campaign_id, limit)).fetchall()
            else:
                rows = self.connection.execute("SELECT payload_json FROM scientific_decisions ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return tuple(ScientificDecision.from_dict(json.loads(row["payload_json"])) for row in rows)
