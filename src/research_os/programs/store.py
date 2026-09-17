"""Durable storage for Research Program snapshots and execution lineage."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading
from typing import Any

from research_os.programs.models import ResearchProgram


class ResearchProgramStore:
    """SQLite store with mutable snapshots and append-only execution links."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock, self.connection:
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS research_programs (
                    program_id TEXT PRIMARY KEY,
                    digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS program_protocols (
                    protocol_id TEXT PRIMARY KEY,
                    protocol_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS program_executions (
                    execution_id TEXT PRIMARY KEY,
                    program_id TEXT NOT NULL,
                    protocol_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    record_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS program_campaign_executions (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL,
                    local_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS program_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS program_syntheses (
                    synthesis_id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL,
                    protocol_id TEXT NOT NULL,
                    synthesis_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS program_reproductions (
                    reproduction_id TEXT PRIMARY KEY,
                    reproduction_hash TEXT NOT NULL,
                    source_execution_id TEXT,
                    reproduced_execution_id TEXT,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_program_exec_program ON program_executions(program_id)")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_program_campaign_exec ON program_campaign_executions(execution_id)")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_program_synthesis_exec ON program_syntheses(execution_id)")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_program_reproduction_source ON program_reproductions(source_execution_id)")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_program_reproduction_target ON program_reproductions(reproduced_execution_id)")

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def save(self, program: ResearchProgram) -> ResearchProgram:
        payload = json.dumps(program.to_dict(), ensure_ascii=False, sort_keys=True, default=str)
        with self._lock, self.connection:
            self.connection.execute(
                """INSERT INTO research_programs(program_id,digest,payload_json,updated_at) VALUES(?,?,?,?)
                   ON CONFLICT(program_id) DO UPDATE SET digest=excluded.digest,payload_json=excluded.payload_json,updated_at=excluded.updated_at""",
                (program.program_id, str(program.digest), payload, str(program.updated_at if hasattr(program, "updated_at") else program.created_at)),
            )
        return program

    def get(self, program_id: str) -> ResearchProgram:
        with self._lock:
            row = self.connection.execute("SELECT payload_json FROM research_programs WHERE program_id=?", (program_id,)).fetchone()
        if row is None:
            raise KeyError(program_id)
        return ResearchProgram(**json.loads(row["payload_json"]))

    def list(self, *, limit: int = 100) -> tuple[ResearchProgram, ...]:
        with self._lock:
            rows = self.connection.execute("SELECT payload_json FROM research_programs ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return tuple(ResearchProgram(**json.loads(row["payload_json"])) for row in rows)

    def save_protocol(self, protocol_id: str, protocol_hash: str, payload: dict[str, Any], created_at: str) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO program_protocols(protocol_id,protocol_hash,payload_json,created_at) VALUES(?,?,?,?) ON CONFLICT(protocol_id) DO UPDATE SET protocol_hash=excluded.protocol_hash,payload_json=excluded.payload_json",
                (protocol_id, protocol_hash, json.dumps(payload, ensure_ascii=False, sort_keys=True), created_at),
            )

    def save_execution(self, record: dict[str, Any]) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                """INSERT INTO program_executions(execution_id,program_id,protocol_id,status,record_hash,payload_json,updated_at)
                   VALUES(?,?,?,?,?,?,?) ON CONFLICT(execution_id) DO UPDATE SET status=excluded.status,
                   record_hash=excluded.record_hash,payload_json=excluded.payload_json,updated_at=excluded.updated_at""",
                (
                    str(record["program_execution_id"]),
                    str(record["program_id"]),
                    str(record["program_protocol_id"]),
                    str(record["status"]),
                    str(record["record_hash"]),
                    json.dumps(record, ensure_ascii=False, sort_keys=True),
                    str(record["updated_at"]),
                ),
            )

    def save_execution_with_campaign(self, record: dict[str, Any], *, local_id: str, status: str, attempt: int, payload: dict[str, Any], created_at: str) -> None:
        """Persist an execution snapshot and its child transition atomically."""
        with self._lock, self.connection:
            self.connection.execute(
                """INSERT INTO program_executions(execution_id,program_id,protocol_id,status,record_hash,payload_json,updated_at)
                   VALUES(?,?,?,?,?,?,?) ON CONFLICT(execution_id) DO UPDATE SET status=excluded.status,
                   record_hash=excluded.record_hash,payload_json=excluded.payload_json,updated_at=excluded.updated_at""",
                (
                    str(record["program_execution_id"]),
                    str(record["program_id"]),
                    str(record["program_protocol_id"]),
                    str(record["status"]),
                    str(record["record_hash"]),
                    json.dumps(record, ensure_ascii=False, sort_keys=True),
                    str(record["updated_at"]),
                ),
            )
            self.connection.execute(
                "INSERT INTO program_campaign_executions(execution_id,local_id,status,attempt,payload_json,created_at) VALUES(?,?,?,?,?,?)",
                (str(record["program_execution_id"]), local_id, status, int(attempt), json.dumps(payload, ensure_ascii=False, sort_keys=True), created_at),
            )

    def append_campaign(self, execution_id: str, local_id: str, status: str, attempt: int, payload: dict[str, Any], created_at: str) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO program_campaign_executions(execution_id,local_id,status,attempt,payload_json,created_at) VALUES(?,?,?,?,?,?)",
                (execution_id, local_id, status, int(attempt), json.dumps(payload, ensure_ascii=False, sort_keys=True), created_at),
            )

    def append_event(self, execution_id: str, event_type: str, payload: dict[str, Any], created_at: str) -> None:
        with self._lock, self.connection:
            self.connection.execute(
                "INSERT INTO program_events(execution_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",
                (execution_id, event_type, json.dumps(payload, ensure_ascii=False, sort_keys=True), created_at),
            )

    def save_synthesis(self, record: dict[str, Any], created_at: str) -> None:
        """Append one immutable synthesis record; an existing ID is a conflict."""
        with self._lock, self.connection:
            existing = self.connection.execute("SELECT synthesis_hash, payload_json FROM program_syntheses WHERE synthesis_id=?", (str(record["synthesis_id"]),)).fetchone()
            if existing is not None:
                if existing["synthesis_hash"] == str(record["synthesis_hash"]):
                    return
                raise ValueError("PROGRAM_SYNTHESIS_ID_CONFLICT")
            self.connection.execute(
                "INSERT INTO program_syntheses(synthesis_id,execution_id,protocol_id,synthesis_hash,payload_json,created_at) VALUES(?,?,?,?,?,?)",
                (str(record["synthesis_id"]), str(record["program_execution_id"]), str(record["program_protocol_id"]), str(record["synthesis_hash"]), json.dumps(record, ensure_ascii=False, sort_keys=True), created_at),
            )

    def get_synthesis(self, synthesis_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute("SELECT payload_json FROM program_syntheses WHERE synthesis_id=?", (synthesis_id,)).fetchone()
        if row is None:
            raise KeyError(synthesis_id)
        return json.loads(row["payload_json"])

    def list_syntheses(self, execution_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self.connection.execute("SELECT payload_json FROM program_syntheses WHERE execution_id=? ORDER BY created_at, synthesis_id", (execution_id,)).fetchall()
        return tuple(json.loads(row["payload_json"]) for row in rows)

    def save_reproduction(self, record: dict[str, Any], created_at: str) -> None:
        """Append one immutable reproduction record; equal replays are idempotent."""
        reproduction_id = str(record["reproduction_id"])
        with self._lock, self.connection:
            existing = self.connection.execute(
                "SELECT reproduction_hash, payload_json FROM program_reproductions WHERE reproduction_id=?",
                (reproduction_id,),
            ).fetchone()
            if existing is not None:
                if existing["reproduction_hash"] == str(record["reproduction_hash"]):
                    return
                raise ValueError("PROGRAM_REPRODUCTION_ID_CONFLICT")
            self.connection.execute(
                """INSERT INTO program_reproductions(
                    reproduction_id,reproduction_hash,source_execution_id,
                    reproduced_execution_id,status,payload_json,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (
                    reproduction_id,
                    str(record["reproduction_hash"]),
                    record.get("source_program_execution_id"),
                    record.get("reproduced_program_execution_id"),
                    str(record["status"]),
                    json.dumps(record, ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )

    def get_reproduction(self, reproduction_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute(
                "SELECT payload_json FROM program_reproductions WHERE reproduction_id=?",
                (reproduction_id,),
            ).fetchone()
        if row is None:
            raise KeyError(reproduction_id)
        return json.loads(row["payload_json"])

    def list_reproductions(self, *, source_execution_id: str | None = None) -> tuple[dict[str, Any], ...]:
        with self._lock:
            if source_execution_id is None:
                rows = self.connection.execute(
                    "SELECT payload_json FROM program_reproductions ORDER BY created_at, reproduction_id"
                ).fetchall()
            else:
                rows = self.connection.execute(
                    "SELECT payload_json FROM program_reproductions WHERE source_execution_id=? ORDER BY created_at, reproduction_id",
                    (source_execution_id,),
                ).fetchall()
        return tuple(json.loads(row["payload_json"]) for row in rows)

    def get_execution(self, execution_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute("SELECT payload_json FROM program_executions WHERE execution_id=?", (execution_id,)).fetchone()
        if row is None:
            raise KeyError(execution_id)
        return json.loads(row["payload_json"])

    def list_campaign_events(self, execution_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self.connection.execute("SELECT local_id,status,attempt,payload_json,created_at FROM program_campaign_executions WHERE execution_id=? ORDER BY event_id", (execution_id,)).fetchall()
        return tuple({"local_id": row["local_id"], "status": row["status"], "attempt": row["attempt"], "payload": json.loads(row["payload_json"]), "created_at": row["created_at"]} for row in rows)


__all__ = ["ResearchProgramStore"]
