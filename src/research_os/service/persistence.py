"""SQLite persistence for chat sessions and ResearchJob transport state.

The experience store deliberately keeps conversation/job payloads separate from
the scientific Ledger tables.  The Ledger remains the source of truth for
immutable runs, evidence, bundles and lineage; this store makes the UI
reopenable after a process restart.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading
from typing import Any

from research_os.service.contracts import ResearchJob, ResearchMessage, ResearchSession


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class ResearchStore:
    """Small transactional store for the operational Oracle experience."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    active_question_id TEXT,
                    active_workflow_id TEXT,
                    active_job_id TEXT,
                    related_run_ids_json TEXT NOT NULL,
                    related_bundle_ids_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES research_sessions(session_id),
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    question_id TEXT,
                    job_id TEXT,
                    references_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_jobs (
                    job_id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES research_sessions(session_id),
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    current_step TEXT,
                    error_code TEXT,
                    first_loss_json TEXT,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_responses (
                    job_id TEXT PRIMARY KEY REFERENCES research_jobs(job_id),
                    session_id TEXT REFERENCES research_sessions(session_id),
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_research_jobs_session ON research_jobs(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_research_messages_session ON research_messages(session_id, timestamp);
                """
            )

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def create_session(self, title: str = "New research", *, tags: list[str] | None = None) -> ResearchSession:
        session = ResearchSession(title=title, tags=list(tags or []))
        self.save_session(session)
        return session

    def save_session(self, session: ResearchSession) -> ResearchSession:
        with self._lock, self.connection:
            self.connection.execute(
                """INSERT INTO research_sessions(session_id,title,created_at,updated_at,status,active_question_id,active_workflow_id,active_job_id,related_run_ids_json,related_bundle_ids_json,tags_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET title=excluded.title,updated_at=excluded.updated_at,status=excluded.status,active_question_id=excluded.active_question_id,active_workflow_id=excluded.active_workflow_id,active_job_id=excluded.active_job_id,related_run_ids_json=excluded.related_run_ids_json,related_bundle_ids_json=excluded.related_bundle_ids_json,tags_json=excluded.tags_json""",
                (session.session_id, session.title, session.created_at, session.updated_at, session.status, session.active_question_id, session.active_workflow_id, session.active_job_id, _json(session.related_run_ids), _json(session.related_bundle_ids), _json(session.tags)),
            )
        return session

    def get_session(self, session_id: str) -> ResearchSession:
        with self._lock:
            row = self.connection.execute("SELECT * FROM research_sessions WHERE session_id = ?", (session_id,)).fetchone()
            if row is None:
                raise KeyError(session_id)
            messages = self.connection.execute("SELECT role,content,timestamp,question_id,job_id,references_json FROM research_messages WHERE session_id=? ORDER BY timestamp,message_id", (session_id,)).fetchall()
        user: list[ResearchMessage] = []
        oracle: list[ResearchMessage] = []
        for item in messages:
            message = ResearchMessage(item["role"], item["content"], item["timestamp"], item["question_id"], item["job_id"], json.loads(item["references_json"]))
            (user if message.role == "user" else oracle).append(message)
        return ResearchSession(
            session_id=row["session_id"], title=row["title"], created_at=row["created_at"], updated_at=row["updated_at"], status=row["status"], active_question_id=row["active_question_id"], active_workflow_id=row["active_workflow_id"], active_job_id=row["active_job_id"], user_messages=user, oracle_messages=oracle, related_run_ids=json.loads(row["related_run_ids_json"]), related_bundle_ids=json.loads(row["related_bundle_ids_json"]), tags=json.loads(row["tags_json"]),
        )

    def list_sessions(self, *, limit: int = 100) -> list[ResearchSession]:
        with self._lock:
            ids = [row["session_id"] for row in self.connection.execute("SELECT session_id FROM research_sessions ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()]
        return [self.get_session(session_id) for session_id in ids]

    def append_message(self, session_id: str, message: ResearchMessage) -> None:
        with self._lock, self.connection:
            self.connection.execute("INSERT INTO research_messages(session_id,role,content,timestamp,question_id,job_id,references_json) VALUES(?,?,?,?,?,?,?)", (session_id, message.role, message.content, message.timestamp, message.question_id, message.job_id, _json(message.references)))
            self.connection.execute("UPDATE research_sessions SET updated_at=? WHERE session_id=?", (message.timestamp, session_id))

    def save_job(self, job: ResearchJob) -> None:
        payload = job.to_dict()
        with self._lock, self.connection:
            self.connection.execute(
                """INSERT INTO research_jobs(job_id,session_id,status,created_at,started_at,completed_at,current_step,error_code,first_loss_json,payload_json)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET session_id=excluded.session_id,status=excluded.status,started_at=excluded.started_at,completed_at=excluded.completed_at,current_step=excluded.current_step,error_code=excluded.error_code,first_loss_json=excluded.first_loss_json,payload_json=excluded.payload_json""",
                (job.job_id, job.session_id, job.status.value, job.created_at, job.started_at, job.completed_at, job.current_step, job.error_code, _json(job.first_loss) if job.first_loss else None, _json(payload)),
            )

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute("SELECT payload_json FROM research_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return json.loads(row["payload_json"])

    def list_jobs(self, session_id: str | None = None, *, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT payload_json FROM research_jobs"
        params: tuple[Any, ...] = ()
        if session_id is not None:
            sql += " WHERE session_id=?"
            params = (session_id,)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params += (limit,)
        with self._lock:
            return [json.loads(row["payload_json"]) for row in self.connection.execute(sql, params).fetchall()]

    def recover_interrupted_jobs(self) -> list[str]:
        """Close non-terminal jobs after a process restart without faking progress."""
        active = {"QUEUED", "PLANNING", "VALIDATING", "RUNNING", "WAITING"}
        recovered: list[str] = []
        with self._lock, self.connection:
            rows = self.connection.execute("SELECT job_id,payload_json FROM research_jobs WHERE status IN (?,?,?,?,?)", tuple(active)).fetchall()
            for row in rows:
                payload = json.loads(row["payload_json"])
                payload["status"] = "FAILED"
                payload["error_code"] = "PROCESS_RESTARTED"
                payload["completed_at"] = payload.get("completed_at") or payload.get("created_at")
                payload.setdefault("progress", []).append({"stage": "recovery", "message": "job marked failed after process restart; no execution was resumed", "completed": True, "metadata": {"error_code": "PROCESS_RESTARTED"}, "timestamp": payload["completed_at"]})
                self.connection.execute("UPDATE research_jobs SET status='FAILED',error_code='PROCESS_RESTARTED',completed_at=?,payload_json=? WHERE job_id=?", (payload["completed_at"], _json(payload), row["job_id"]))
                recovered.append(row["job_id"])
        return recovered

    def save_response(self, job_id: str, session_id: str | None, payload: dict[str, Any], *, created_at: str) -> None:
        with self._lock, self.connection:
            self.connection.execute("INSERT INTO research_responses(job_id,session_id,created_at,payload_json) VALUES(?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET payload_json=excluded.payload_json,session_id=excluded.session_id", (job_id, session_id, created_at, _json(payload)))

    def get_response(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.connection.execute("SELECT payload_json FROM research_responses WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return json.loads(row["payload_json"])

    def list_responses(self, session_id: str | None = None, *, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT payload_json FROM research_responses"
        params: tuple[Any, ...] = ()
        if session_id is not None:
            sql += " WHERE session_id=?"
            params = (session_id,)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params += (limit,)
        with self._lock:
            return [json.loads(row["payload_json"]) for row in self.connection.execute(sql, params).fetchall()]
