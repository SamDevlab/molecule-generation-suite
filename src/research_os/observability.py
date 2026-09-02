"""Small, dependency-free structured logging boundary for Research OS runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Any, Mapping


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class StructuredEvent:
    """Stable event shape used by the runner and CLI.

    The event deliberately carries identifiers and status separately from the
    human message so JSON log consumers do not need to parse free text.
    """

    event: str
    run_id: str | None = None
    lab: str | None = None
    step_id: str | None = None
    status: str | None = None
    message: str | None = None
    timestamp: str = field(default_factory=_now)
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "timestamp": self.timestamp,
            "event": self.event,
            "run_id": self.run_id,
            "lab": self.lab,
            "step_id": self.step_id,
            "status": self.status,
            "message": self.message,
        }
        data.update(self.fields)
        return {key: value for key, value in data.items() if value is not None}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, default=str)


class StructuredLogger:
    """Emit one JSON object per event through a standard logger."""

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("research_os")

    def emit(
        self,
        event: str,
        *,
        run_id: str | None = None,
        lab: str | None = None,
        step_id: str | None = None,
        status: str | None = None,
        message: str | None = None,
        fields: Mapping[str, Any] | None = None,
    ) -> StructuredEvent:
        record = StructuredEvent(event, run_id=run_id, lab=lab, step_id=step_id, status=status, message=message, fields=dict(fields or {}))
        self.logger.info(record.to_json())
        return record
