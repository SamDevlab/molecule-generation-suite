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


@dataclass
class ObservabilityMetrics:
    """Counters/timings kept separate from scientific evidence."""

    run_durations_seconds: list[float] = field(default_factory=list)
    workflow_durations_seconds: list[float] = field(default_factory=list)
    engine_availability: dict[str, int] = field(default_factory=dict)
    failure_rates: dict[str, int] = field(default_factory=dict)
    first_loss_counts: dict[str, int] = field(default_factory=dict)
    cache_hits: int = 0
    job_states: dict[str, int] = field(default_factory=dict)

    def observe_engine(self, engine_id: str, available: bool) -> None:
        key = "available" if available else "unavailable"
        self.engine_availability[f"{engine_id}:{key}"] = self.engine_availability.get(f"{engine_id}:{key}", 0) + 1

    def observe_state(self, state: str) -> None:
        self.job_states[state] = self.job_states.get(state, 0) + 1

    def observe_first_loss(self, rule_id: str | None) -> None:
        if rule_id:
            self.first_loss_counts[rule_id] = self.first_loss_counts.get(rule_id, 0) + 1

    def observe_failure(self, category: str) -> None:
        self.failure_rates[category] = self.failure_rates.get(category, 0) + 1

    def to_dict(self) -> dict[str, Any]:
        return {"run_durations_seconds": list(self.run_durations_seconds), "workflow_durations_seconds": list(self.workflow_durations_seconds), "engine_availability": dict(self.engine_availability), "failure_rates": dict(self.failure_rates), "first_loss_counts": dict(self.first_loss_counts), "cache_hits": self.cache_hits, "job_states": dict(self.job_states)}
