"""Persistent campaign history, separate from the immutable scientific Ledger."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading
from typing import Any

from research_os.campaigns.models import ResearchCampaign


class CampaignStore:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock, self.connection:
            self.connection.execute("CREATE TABLE IF NOT EXISTS research_campaigns (campaign_id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, payload_json TEXT NOT NULL)")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_research_campaigns_updated ON research_campaigns(updated_at)")

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def save(self, campaign: ResearchCampaign) -> ResearchCampaign:
        payload = json.dumps(campaign.to_dict(), ensure_ascii=False, sort_keys=True, default=str)
        with self._lock, self.connection:
            self.connection.execute("INSERT INTO research_campaigns(campaign_id,status,created_at,updated_at,payload_json) VALUES(?,?,?,?,?) ON CONFLICT(campaign_id) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at,payload_json=excluded.payload_json", (campaign.campaign_id, campaign.status.value, campaign.created_at, campaign.updated_at, payload))
        return campaign

    def get(self, campaign_id: str) -> ResearchCampaign:
        with self._lock:
            row = self.connection.execute("SELECT payload_json FROM research_campaigns WHERE campaign_id=?", (campaign_id,)).fetchone()
        if row is None:
            raise KeyError(campaign_id)
        return ResearchCampaign(**json.loads(row["payload_json"]))

    def list(self, *, limit: int = 100) -> tuple[ResearchCampaign, ...]:
        with self._lock:
            rows = self.connection.execute("SELECT payload_json FROM research_campaigns ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return tuple(ResearchCampaign(**json.loads(row["payload_json"])) for row in rows)


class DeclarativeCampaignStore:
    """Durable append-only execution history for declarative campaigns.

    This store deliberately lives beside, rather than inside, the legacy
    ``research_campaigns`` table.  Existing campaign records therefore keep
    their historical schema while a declarative execution gets an immutable
    plan plus append-only child attempts and events.
    """

    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock, self.connection:
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS campaign_executions (
                    execution_id TEXT PRIMARY KEY,
                    campaign_protocol_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    record_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS campaign_child_runs (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL,
                    child_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS campaign_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def save_snapshot(self, record: dict[str, Any]) -> None:
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self._lock, self.connection:
            self.connection.execute(
                """INSERT INTO campaign_executions(execution_id,campaign_protocol_id,status,record_hash,payload_json,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(execution_id) DO UPDATE SET status=excluded.status,
                   record_hash=excluded.record_hash,payload_json=excluded.payload_json,updated_at=excluded.updated_at""",
                (
                    str(record["campaign_execution_id"]),
                    str(record["campaign_protocol_id"]),
                    str(record["status"]),
                    str(record["record_hash"]),
                    payload,
                    str(record["updated_at"]),
                ),
            )

    def append_child(self, execution_id: str, child_id: str, attempt: int, status: str, payload: dict[str, Any], created_at: str) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO campaign_child_runs(execution_id,child_id,attempt,status,payload_json,created_at) VALUES(?,?,?,?,?,?)",
                (execution_id, child_id, int(attempt), status, json.dumps(payload, ensure_ascii=False, sort_keys=True), created_at),
            )

    def append_event(self, execution_id: str, event_type: str, payload: dict[str, Any], created_at: str) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO campaign_events(execution_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",
                (execution_id, event_type, json.dumps(payload, ensure_ascii=False, sort_keys=True), created_at),
            )

    def get_snapshot(self, execution_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute("SELECT payload_json FROM campaign_executions WHERE execution_id=?", (execution_id,)).fetchone()
        if row is None:
            raise KeyError(execution_id)
        return json.loads(row["payload_json"])

    def list_child_attempts(self, execution_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT child_id,attempt,status,payload_json,created_at FROM campaign_child_runs WHERE execution_id=? ORDER BY event_id",
                (execution_id,),
            ).fetchall()
        return tuple({"child_id": row["child_id"], "attempt": row["attempt"], "status": row["status"], "payload": json.loads(row["payload_json"]), "created_at": row["created_at"]} for row in rows)
