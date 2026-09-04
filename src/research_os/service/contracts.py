"""Transport-safe service contracts for a chat-first Research OS UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResearchJobStatus(str, Enum):
    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    VALIDATING = "VALIDATING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class ResearchMessage:
    """A chat message, kept separate from scientific evidence records."""

    role: str
    content: str
    timestamp: str = field(default_factory=_now)
    question_id: str | None = None
    job_id: str | None = None
    references: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchSession:
    """Persistent conversational context around immutable Ledger executions."""

    session_id: str = field(default_factory=lambda: f"SESSION-{uuid.uuid4().hex[:12].upper()}")
    title: str = "New research"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    status: str = "ACTIVE"
    active_question_id: str | None = None
    active_workflow_id: str | None = None
    active_job_id: str | None = None
    user_messages: list[ResearchMessage] = field(default_factory=list)
    oracle_messages: list[ResearchMessage] = field(default_factory=list)
    related_run_ids: list[str] = field(default_factory=list)
    related_bundle_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def add_user_message(self, content: str, *, question_id: str | None = None, job_id: str | None = None) -> ResearchMessage:
        message = ResearchMessage("user", content, question_id=question_id, job_id=job_id)
        self.user_messages.append(message)
        self.updated_at = _now()
        return message

    def add_oracle_message(self, content: str, *, job_id: str | None = None, references: dict[str, Any] | None = None) -> ResearchMessage:
        message = ResearchMessage("oracle", content, job_id=job_id, references=dict(references or {}))
        self.oracle_messages.append(message)
        self.updated_at = _now()
        return message

    @property
    def messages(self) -> list[ResearchMessage]:
        return sorted((*self.user_messages, *self.oracle_messages), key=lambda item: item.timestamp)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["user_messages"] = [item.to_dict() for item in self.user_messages]
        data["oracle_messages"] = [item.to_dict() for item in self.oracle_messages]
        return data


@dataclass(frozen=True)
class ResearchProgress:
    stage: str
    message: str
    completed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchJob:
    question_id: str
    session_id: str | None = None
    plan_id: str | None = None
    workflow_id: str | None = None
    status: ResearchJobStatus = ResearchJobStatus.QUEUED
    progress: list[ResearchProgress] = field(default_factory=list)
    current_step: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    job_id: str = field(default_factory=lambda: f"JOB-{uuid.uuid4().hex[:12].upper()}")
    created_at: str = field(default_factory=_now)
    error_code: str | None = None
    first_loss: dict[str, Any] | None = None

    def emit(self, stage: str, message: str, *, completed: bool = False, **metadata: Any) -> None:
        self.progress.append(ResearchProgress(stage, message, completed, metadata))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["progress"] = [item.to_dict() for item in self.progress]
        return data
