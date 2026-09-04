"""Immutable, auditable models for bounded autonomous research programs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence
import uuid

from research_os.core.hashing import sha256_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tuple(values: Sequence[Any] | None) -> tuple[Any, ...]:
    return tuple(values or ())


class ResearchProgramStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    PAUSED_EXTERNAL_BLOCKER = "PAUSED_EXTERNAL_BLOCKER"
    NO_PROGRESS = "NO_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"


class UtilityRecommendation(str, Enum):
    EXECUTE = "EXECUTE"
    DEFER = "DEFER"
    SKIP_REDUNDANT = "SKIP_REDUNDANT"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
    NO_EXPECTED_INFORMATION_GAIN = "NO_EXPECTED_INFORMATION_GAIN"
    REJECT_UNSAFE = "REJECT_UNSAFE"
    REJECT_OUT_OF_SCOPE = "REJECT_OUT_OF_SCOPE"


class ProgramExecutionStatus(str, Enum):
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"
    STOPPED = "STOPPED"


@dataclass(frozen=True)
class ResearchProgram:
    program_id: str
    title: str
    domain: str
    objective: str
    motivation: str
    initial_problem: str
    research_questions: tuple[Mapping[str, Any], ...] = ()
    campaign_ids: tuple[str, ...] = ()
    current_question_id: str | None = None
    resolved_question_ids: tuple[str, ...] = ()
    open_question_ids: tuple[str, ...] = ()
    research_gap_ids: tuple[str, ...] = ()
    scientific_decision_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    dataset_ids: tuple[str, ...] = ()
    model_ids: tuple[str, ...] = ()
    engine_ids: tuple[str, ...] = ()
    max_campaigns: int = 10
    max_iterations: int = 10
    max_runs: int = 10
    max_sources: int = 10
    max_candidates: int = 100
    max_failures: int = 3
    status: ResearchProgramStatus | str = ResearchProgramStatus.CREATED
    stop_reason: str | None = None
    created_at: str = field(default_factory=_now)
    completed_at: str | None = None
    parent_program_id: str | None = None
    digest: str | None = None

    def __post_init__(self) -> None:
        if not self.program_id.strip() or not self.title.strip() or not self.domain.strip() or not self.objective.strip() or not self.initial_problem.strip():
            raise ValueError("ResearchProgram requires identity, objective and initial_problem")
        status = self.status if isinstance(self.status, ResearchProgramStatus) else ResearchProgramStatus(str(self.status))
        object.__setattr__(self, "status", status)
        for name in ("research_questions", "campaign_ids", "resolved_question_ids", "open_question_ids", "research_gap_ids", "scientific_decision_ids", "source_ids", "dataset_ids", "model_ids", "engine_ids"):
            values = tuple(getattr(self, name) or ())
            object.__setattr__(self, name, values)
        limits = ("max_campaigns", "max_iterations", "max_runs", "max_sources", "max_candidates", "max_failures")
        if any(not isinstance(getattr(self, name), int) or getattr(self, name) < 0 for name in limits):
            raise ValueError("ResearchProgram resource limits must be non-negative integers")
        for question in self.research_questions:
            if not isinstance(question, Mapping) or not str(question.get("gap_it_attempts_to_resolve") or "").strip():
                raise ValueError("every ResearchProgram question must declare gap_it_attempts_to_resolve")
        if self.digest is None:
            object.__setattr__(self, "digest", sha256_json(self._hash_payload()))

    def _hash_payload(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("digest", None)
        data["status"] = self.status.value
        return data

    @property
    def valid(self) -> bool:
        return self.digest == sha256_json(self._hash_payload())

    def to_dict(self) -> dict[str, Any]:
        data = self._hash_payload()
        data["digest"] = self.digest
        return data

    def with_status(self, status: ResearchProgramStatus | str, *, stop_reason: str | None = None, completed_at: str | None = None) -> "ResearchProgram":
        return ResearchProgram(**{**self._hash_payload(), "status": status, "stop_reason": stop_reason if stop_reason is not None else self.stop_reason, "completed_at": completed_at if completed_at is not None else self.completed_at})


@dataclass(frozen=True)
class ResearchStepUtilityAssessment:
    assessment_id: str
    program_id: str
    proposed_step_id: str
    gap_addressed: str
    question_addressed: str
    existing_evidence_ids: tuple[str, ...]
    expected_information_gain: str | Mapping[str, Any]
    redundancy_risk: str | Mapping[str, Any]
    required_resources: tuple[str, ...]
    required_engines: tuple[str, ...]
    required_datasets: tuple[str, ...]
    external_dependency: str | None
    execution_scope: str
    scientific_risk: str
    recommendation: UtilityRecommendation | str
    rationale: str
    created_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.gap_addressed.strip() or not self.question_addressed.strip() or not self.execution_scope.strip() or not self.rationale.strip():
            raise ValueError("ResearchStepUtilityAssessment requires gap, question, scope and rationale")
        recommendation = self.recommendation if isinstance(self.recommendation, UtilityRecommendation) else UtilityRecommendation(str(self.recommendation))
        object.__setattr__(self, "recommendation", recommendation)
        for name in ("existing_evidence_ids", "required_resources", "required_engines", "required_datasets"):
            object.__setattr__(self, name, tuple(str(item) for item in getattr(self, name) or ()))
        if isinstance(self.expected_information_gain, Mapping) and any(str(key).lower() in {"score", "value", "universal_score", "scientific_value"} for key in self.expected_information_gain):
            raise ValueError("expected information gain cannot be a universal numeric score")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["recommendation"] = self.recommendation.value
        for name in ("existing_evidence_ids", "required_resources", "required_engines", "required_datasets"):
            data[name] = list(getattr(self, name))
        return data


@dataclass(frozen=True)
class KnowledgeGainAssessment:
    program_id: str
    new_supported_claim_ids: tuple[str, ...] = ()
    new_partial_claim_ids: tuple[str, ...] = ()
    new_rejected_claim_ids: tuple[str, ...] = ()
    revised_claim_ids: tuple[str, ...] = ()
    resolved_gap_ids: tuple[str, ...] = ()
    partially_resolved_gap_ids: tuple[str, ...] = ()
    new_gap_ids: tuple[str, ...] = ()
    new_source_ids: tuple[str, ...] = ()
    new_dataset_ids: tuple[str, ...] = ()
    new_evidence_ids: tuple[str, ...] = ()
    unresolved_uncertainty: tuple[str, ...] = ()
    summary: str = ""

    def __post_init__(self) -> None:
        for name in ("new_supported_claim_ids", "new_partial_claim_ids", "new_rejected_claim_ids", "revised_claim_ids", "resolved_gap_ids", "partially_resolved_gap_ids", "new_gap_ids", "new_source_ids", "new_dataset_ids", "new_evidence_ids", "unresolved_uncertainty"):
            object.__setattr__(self, name, tuple(str(item) for item in getattr(self, name) or ()))
        if not self.summary.strip():
            raise ValueError("KnowledgeGainAssessment requires a summary")

    @property
    def has_positive_gain(self) -> bool:
        return bool(self.new_evidence_ids or self.new_source_ids or self.new_dataset_ids or self.revised_claim_ids or self.resolved_gap_ids or self.partially_resolved_gap_ids or self.new_supported_claim_ids or self.new_partial_claim_ids or self.new_rejected_claim_ids)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for name in data:
            if isinstance(data[name], tuple):
                data[name] = list(data[name])
        return data


__all__ = ["KnowledgeGainAssessment", "ProgramExecutionStatus", "ResearchProgram", "ResearchProgramStatus", "ResearchStepUtilityAssessment", "UtilityRecommendation"]
