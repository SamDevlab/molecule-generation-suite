"""Research memory facade over immutable records and optional Ledger queries."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from research_os.oracle.models import ResearchPlan, ResearchQuestion


@dataclass(frozen=True)
class MemoryRecord:
    kind: str
    record_id: str
    payload: dict[str, Any]
    rerun_of: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResearchMemory:
    """Never edits a previous record; continuation creates a new record."""

    def __init__(self, ledger: Any | None = None):
        self.ledger = ledger
        self._records: list[MemoryRecord] = []

    def remember(self, kind: str, record_id: str, payload: dict[str, Any], *, rerun_of: str | None = None) -> MemoryRecord:
        record = MemoryRecord(kind, record_id, dict(payload), rerun_of)
        self._records.append(record)
        return record

    def search(self, text: str = "", *, kind: str | None = None) -> tuple[MemoryRecord, ...]:
        needle = text.lower().strip()
        return tuple(record for record in self._records if (kind is None or record.kind == kind) and (not needle or needle in str(record.payload).lower()))

    def continue_research(self, previous_plan: ResearchPlan, question: ResearchQuestion | None = None) -> tuple[ResearchQuestion, ResearchPlan]:
        new_question = question or ResearchQuestion(f"Continue research for {previous_plan.question_id}", "continuation", f"Continue the previous research plan {previous_plan.plan_id}", constraints={"rerun_of": previous_plan.plan_id}, required_evidence_level=ResearchQuestion.__dataclass_fields__["required_evidence_level"].default)
        new_plan = ResearchPlan(new_question.question_id, previous_plan.steps, previous_plan.assumptions, previous_plan.required_sources, previous_plan.expected_outputs, previous_plan.risk_flags, previous_plan.claim_targets, rerun_of=previous_plan.plan_id)
        return new_question, new_plan

    def ledger_snapshot(self) -> dict[str, Any]:
        if self.ledger is None:
            return {"runs": [], "workflows": []}
        return {"runs": [item.to_dict() for item in self.ledger.list_runs(limit=1_000_000)], "workflows": [item.to_dict() for item in self.ledger.list_workflows(limit=1_000_000)]}

