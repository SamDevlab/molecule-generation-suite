"""Traceable, non-numeric research prioritization models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence
import uuid

from research_os.core.hashing import sha256_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tuple(values: Sequence[Any] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in values or ())


class PriorityRecommendation(str, Enum):
    PRIORITIZE_NOW = "PRIORITIZE_NOW"
    SECONDARY = "SECONDARY"
    DEFER = "DEFER"
    BLOCKED = "BLOCKED"
    LOW_INFORMATION_GAIN = "LOW_INFORMATION_GAIN"
    UNSAFE = "UNSAFE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass(frozen=True)
class ResearchPriorityAssessment:
    assessment_id: str
    candidate_question_id: str
    candidate_gap_id: str
    scientific_relevance: str | Mapping[str, Any]
    current_evidence: tuple[str, ...]
    target_evidence: tuple[str, ...]
    resolvability: str
    expected_information_gain: str | Mapping[str, Any]
    redundancy_risk: str
    required_engine_state: tuple[str, ...]
    required_dataset_state: tuple[str, ...]
    required_source_state: tuple[str, ...]
    external_dependency: str | None
    execution_scope: str
    safety_status: str
    recommendation: PriorityRecommendation | str
    rationale: str
    created_at: str = field(default_factory=_now)
    supersedes_assessment_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("current_evidence", "target_evidence", "required_engine_state", "required_dataset_state", "required_source_state"):
            object.__setattr__(self, name, _tuple(getattr(self, name)))
        recommendation = self.recommendation if isinstance(self.recommendation, PriorityRecommendation) else PriorityRecommendation(str(self.recommendation))
        object.__setattr__(self, "recommendation", recommendation)
        if not self.candidate_question_id.strip() or not self.candidate_gap_id.strip() or not self.execution_scope.strip() or not self.rationale.strip():
            raise ValueError("ResearchPriorityAssessment requires candidate, gap, scope and rationale")
        if isinstance(self.expected_information_gain, Mapping) and any(str(key).lower() in {"score", "value", "priority", "universal_score"} for key in self.expected_information_gain):
            raise ValueError("priority cannot contain a universal hidden score")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["recommendation"] = self.recommendation.value
        for name in ("current_evidence", "target_evidence", "required_engine_state", "required_dataset_state", "required_source_state"):
            data[name] = list(getattr(self, name))
        return data


@dataclass(frozen=True)
class PriorityQueueEntry:
    position: int
    assessment_id: str
    candidate_question_id: str
    reason_for_order: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchPriorityQueue:
    queue_id: str
    entries: tuple[PriorityQueueEntry, ...]
    assessment_history: tuple[ResearchPriorityAssessment, ...] = ()
    created_at: str = field(default_factory=_now)
    digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries or ()))
        object.__setattr__(self, "assessment_history", tuple(self.assessment_history or ()))
        if self.digest is None:
            object.__setattr__(self, "digest", sha256_json(self._hash_payload()))

    @classmethod
    def from_assessments(cls, assessments: Sequence[ResearchPriorityAssessment], *, queue_id: str | None = None, history: Sequence[ResearchPriorityAssessment] = ()) -> "ResearchPriorityQueue":
        values = tuple(assessments)
        policy = {PriorityRecommendation.PRIORITIZE_NOW: 0, PriorityRecommendation.SECONDARY: 1, PriorityRecommendation.DEFER: 2, PriorityRecommendation.BLOCKED: 3, PriorityRecommendation.LOW_INFORMATION_GAIN: 4, PriorityRecommendation.UNSAFE: 5, PriorityRecommendation.OUT_OF_SCOPE: 6}
        ordered = sorted(values, key=lambda item: (policy[item.recommendation], item.candidate_gap_id, item.candidate_question_id))
        entries = tuple(PriorityQueueEntry(index, item.assessment_id, item.candidate_question_id, cls._reason(item, index)) for index, item in enumerate(ordered, 1))
        return cls(queue_id or f"QUEUE-{uuid.uuid4().hex[:12].upper()}", entries, (*history, *values))

    @staticmethod
    def _reason(item: ResearchPriorityAssessment, position: int) -> str:
        if item.recommendation == PriorityRecommendation.PRIORITIZE_NOW:
            return "ordered first because the gap is important, locally actionable and could change a decision"
        if item.recommendation == PriorityRecommendation.LOW_INFORMATION_GAIN:
            return "ordered after actionable gaps because the proposed repetition adds little information"
        if item.recommendation == PriorityRecommendation.BLOCKED:
            return "retained after actionable work because an external dependency blocks execution"
        if item.recommendation == PriorityRecommendation.UNSAFE:
            return "kept out of executable positions because the requested scope violates safety boundaries"
        return f"ordered by the declared recommendation and explicit gap state; queue position {position} is not a scientific ranking value"

    @property
    def valid(self) -> bool:
        return self.digest == sha256_json(self._hash_payload())

    def reorder(self, assessments: Sequence[ResearchPriorityAssessment]) -> "ResearchPriorityQueue":
        return ResearchPriorityQueue.from_assessments(assessments, queue_id=self.queue_id, history=self.assessment_history)

    def assessment(self, candidate_question_id: str) -> ResearchPriorityAssessment:
        ids = {entry.assessment_id for entry in self.entries if entry.candidate_question_id == candidate_question_id}
        for item in reversed(self.assessment_history):
            if item.assessment_id in ids:
                return item
        raise KeyError(candidate_question_id)

    def _hash_payload(self) -> dict[str, Any]:
        return {"queue_id": self.queue_id, "entries": [item.to_dict() for item in self.entries], "assessment_history": [item.to_dict() for item in self.assessment_history], "created_at": self.created_at}

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_payload(), "digest": self.digest}


__all__ = ["PriorityRecommendation", "ResearchPriorityAssessment", "ResearchPriorityQueue"]
