"""Machine-readable contracts for the v3.7 decision benchmark.

The benchmark records the decision boundary and its invariants.  It does not
collapse heterogeneous scientific outcomes into an accuracy score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
import uuid

from research_os.core.hashing import sha256_json


def _tuple(values: Sequence[Any] | None) -> tuple[Any, ...]:
    return tuple(values or ())


def _json(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _json(value.to_dict())
    if isinstance(value, Mapping):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


@dataclass(frozen=True)
class DecisionBenchmarkCase:
    """One executed decision question and its auditable result."""

    case_id: str
    category: str
    domain: str
    question: str
    question_language: str
    criteria: tuple[Mapping[str, Any], ...]
    source_ids: tuple[str, ...]
    dataset_ids: tuple[str, ...]
    model_ids: tuple[str, ...]
    engine_ids: tuple[str, ...]
    expected_invariants: tuple[str, ...]
    expected_status_optional: str | None
    actual_status: str
    evidence_ids: tuple[str, ...]
    OOD: bool | None
    uncertainty: tuple[str, ...]
    conditions: Mapping[str, Any]
    decision_id: str
    audit_result: Mapping[str, Any]
    notes: tuple[str, ...] = ()
    real: bool = False
    generated_by_codex: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "criteria", tuple(dict(item) for item in self.criteria))
        for name in ("source_ids", "dataset_ids", "model_ids", "engine_ids", "expected_invariants", "evidence_ids", "uncertainty", "notes"):
            object.__setattr__(self, name, tuple(str(item) for item in getattr(self, name)))
        object.__setattr__(self, "conditions", dict(self.conditions or {}))
        object.__setattr__(self, "audit_result", dict(self.audit_result or {}))
        object.__setattr__(self, "actual_status", str(self.actual_status))
        if self.expected_status_optional is not None:
            object.__setattr__(self, "expected_status_optional", str(self.expected_status_optional))

    def to_dict(self) -> dict[str, Any]:
        return _json({
            "case_id": self.case_id,
            "category": self.category,
            "domain": self.domain,
            "question": self.question,
            "question_language": self.question_language,
            "criteria": list(self.criteria),
            "source_ids": list(self.source_ids),
            "dataset_ids": list(self.dataset_ids),
            "model_ids": list(self.model_ids),
            "engine_ids": list(self.engine_ids),
            "expected_invariants": list(self.expected_invariants),
            "expected_status_optional": self.expected_status_optional,
            "actual_status": self.actual_status,
            "evidence_ids": list(self.evidence_ids),
            "OOD": self.OOD,
            "uncertainty": list(self.uncertainty),
            "conditions": dict(self.conditions),
            "decision_id": self.decision_id,
            "audit_result": dict(self.audit_result),
            "notes": list(self.notes),
            "real": self.real,
            "generated_by_codex": self.generated_by_codex,
        })

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DecisionBenchmarkCase":
        return cls(
            case_id=str(payload["case_id"]),
            category=str(payload["category"]),
            domain=str(payload["domain"]),
            question=str(payload["question"]),
            question_language=str(payload["question_language"]),
            criteria=tuple(payload.get("criteria") or ()),
            source_ids=tuple(payload.get("source_ids") or ()),
            dataset_ids=tuple(payload.get("dataset_ids") or ()),
            model_ids=tuple(payload.get("model_ids") or ()),
            engine_ids=tuple(payload.get("engine_ids") or ()),
            expected_invariants=tuple(payload.get("expected_invariants") or ()),
            expected_status_optional=payload.get("expected_status_optional"),
            actual_status=str(payload["actual_status"]),
            evidence_ids=tuple(payload.get("evidence_ids") or ()),
            OOD=payload.get("OOD"),
            uncertainty=tuple(payload.get("uncertainty") or ()),
            conditions=dict(payload.get("conditions") or {}),
            decision_id=str(payload.get("decision_id") or ""),
            audit_result=dict(payload.get("audit_result") or {}),
            notes=tuple(payload.get("notes") or ()),
            real=bool(payload.get("real", False)),
            generated_by_codex=bool(payload.get("generated_by_codex", False)),
        )


@dataclass(frozen=True)
class SemanticDecisionConsistency:
    """Outcome comparison for semantically equivalent question variants."""

    base_case: str
    paraphrase_cases: tuple[str, ...]
    decision_statuses: tuple[str, ...]
    evidence_sets: tuple[tuple[str, ...], ...]
    criteria_sets: tuple[tuple[str, ...], ...]
    consistent: bool
    divergence_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "paraphrase_cases", tuple(str(item) for item in self.paraphrase_cases))
        object.__setattr__(self, "decision_statuses", tuple(str(item) for item in self.decision_statuses))
        object.__setattr__(self, "evidence_sets", tuple(tuple(str(value) for value in item) for item in self.evidence_sets))
        object.__setattr__(self, "criteria_sets", tuple(tuple(str(value) for value in item) for item in self.criteria_sets))

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_case": self.base_case,
            "paraphrase_cases": list(self.paraphrase_cases),
            "decision_statuses": list(self.decision_statuses),
            "evidence_sets": [list(item) for item in self.evidence_sets],
            "criteria_sets": [list(item) for item in self.criteria_sets],
            "consistent": self.consistent,
            "divergence_reason": self.divergence_reason,
        }


@dataclass(frozen=True)
class ScientificDecisionBenchmark:
    """Sealed aggregate benchmark report with explicit gate metrics."""

    benchmark_id: str
    protocol_version: str
    commit: str
    environment_hash: str
    started_at: str
    completed_at: str
    case_ids: tuple[str, ...]
    total_cases: int
    real_cases: int
    fixture_cases: int
    supported_decisions: int
    provisional_decisions: int
    no_decisions: int
    rejected_requests: int
    indeterminate_cases: int
    invariant_failures: int
    false_supported_decisions: int
    false_no_decisions: int
    digest: str = field(default="", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_ids", tuple(str(item) for item in self.case_ids))
        object.__setattr__(self, "digest", sha256_json(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "protocol_version": self.protocol_version,
            "commit": self.commit,
            "environment_hash": self.environment_hash,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "case_ids": list(self.case_ids),
            "total_cases": self.total_cases,
            "real_cases": self.real_cases,
            "fixture_cases": self.fixture_cases,
            "supported_decisions": self.supported_decisions,
            "provisional_decisions": self.provisional_decisions,
            "no_decisions": self.no_decisions,
            "rejected_requests": self.rejected_requests,
            "indeterminate_cases": self.indeterminate_cases,
            "invariant_failures": self.invariant_failures,
            "false_supported_decisions": self.false_supported_decisions,
            "false_no_decisions": self.false_no_decisions,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}

    @classmethod
    def from_cases(cls, cases: Sequence[DecisionBenchmarkCase], *, commit: str, environment_hash: str, started_at: str, completed_at: str, benchmark_id: str | None = None, protocol_version: str = "research-os.v3.7.decision-benchmark.v1") -> "ScientificDecisionBenchmark":
        values = tuple(cases)
        statuses = tuple(item.actual_status for item in values)
        return cls(
            benchmark_id or f"BENCH-V37-{uuid.uuid4().hex[:12].upper()}",
            protocol_version,
            commit,
            environment_hash,
            started_at,
            completed_at,
            tuple(item.case_id for item in values),
            len(values),
            sum(item.real for item in values),
            sum(not item.real for item in values),
            sum(item.actual_status == "SUPPORTED_DECISION" for item in values),
            sum(item.actual_status == "PROVISIONAL_DECISION" for item in values),
            sum(item.actual_status.startswith("NO_DECISION") for item in values),
            sum(item.actual_status == "REJECTED_DECISION_REQUEST" for item in values),
            sum(item.actual_status == "INDETERMINATE" for item in values),
            sum(not bool(item.audit_result.get("passed", False)) for item in values),
            sum(bool(item.audit_result.get("false_supported_flags")) for item in values),
            sum(bool(item.audit_result.get("false_no_decision_flags")) for item in values),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificDecisionBenchmark":
        fields = dict(payload)
        fields.pop("digest", None)
        return cls(**fields)
