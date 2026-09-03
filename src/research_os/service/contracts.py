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
    plan_id: str | None = None
    workflow_id: str | None = None
    status: ResearchJobStatus = ResearchJobStatus.QUEUED
    progress: list[ResearchProgress] = field(default_factory=list)
    current_step: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    job_id: str = field(default_factory=lambda: f"JOB-{uuid.uuid4().hex[:12].upper()}")

    def emit(self, stage: str, message: str, *, completed: bool = False, **metadata: Any) -> None:
        self.progress.append(ResearchProgress(stage, message, completed, metadata))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["progress"] = [item.to_dict() for item in self.progress]
        return data

