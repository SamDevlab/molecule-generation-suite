"""Typed contracts for source-backed scientific campaigns.

Campaign objects are coordination records.  They never turn a model answer or
an internet citation into scientific evidence; evidence remains attached to
sealed Research OS runs and bundles.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
import uuid

from research_os.core.hashing import sha256_json
from research_os.core.types import EvidenceLevel


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    return tuple(str(item) for item in (value or ()) if item is not None and str(item))


class CampaignStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    SELECTED = "SELECTED"
    PLANNING = "PLANNING"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INDETERMINATE = "INDETERMINATE"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"


class ConflictStatus(str, Enum):
    OPEN = "OPEN"
    CONDITIONALLY_RESOLVED = "CONDITIONALLY_RESOLVED"
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class ProblemCandidate:
    problem_id: str
    title: str
    domain: str
    real_world_context: str
    scientific_question: str
    why_it_matters: str
    sources: tuple[str, ...]
    available_datasets: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    required_engines: tuple[str, ...]
    achievable_evidence_level: EvidenceLevel
    expected_blockers: tuple[str, ...]
    safety: tuple[str, ...]
    source_quality: tuple[str, ...] = ()
    executable_now: bool = False
    created_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sources", _tuple(self.sources))
        object.__setattr__(self, "available_datasets", _tuple(self.available_datasets))
        object.__setattr__(self, "required_capabilities", _tuple(self.required_capabilities))
        object.__setattr__(self, "required_engines", _tuple(self.required_engines))
        object.__setattr__(self, "expected_blockers", _tuple(self.expected_blockers))
        object.__setattr__(self, "safety", _tuple(self.safety))
        object.__setattr__(self, "source_quality", _tuple(self.source_quality))
        object.__setattr__(self, "achievable_evidence_level", self.achievable_evidence_level if isinstance(self.achievable_evidence_level, EvidenceLevel) else EvidenceLevel(str(self.achievable_evidence_level)))
        if not self.problem_id.strip() or not self.title.strip() or not self.domain.strip():
            raise ValueError("ProblemCandidate requires problem_id, title and domain")
        if not self.sources:
            raise ValueError("ProblemCandidate must cite at least one registered source")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for name in ("sources", "available_datasets", "required_capabilities", "required_engines", "expected_blockers", "safety", "source_quality"):
            data[name] = list(getattr(self, name))
        data["achievable_evidence_level"] = self.achievable_evidence_level.value
        return data


@dataclass(frozen=True)
class SourceConflict:
    conflict_id: str
    topic: str
    source_a: str
    source_b: str
    disagreement: str
    conditions_difference: str
    resolution_status: ConflictStatus = ConflictStatus.OPEN
    resolution: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "resolution_status", self.resolution_status if isinstance(self.resolution_status, ConflictStatus) else ConflictStatus(str(self.resolution_status)))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["resolution_status"] = self.resolution_status.value
        return data


@dataclass(frozen=True)
class ResearchGap:
    gap_id: str
    claim: str
    current_evidence: tuple[str, ...]
    required_evidence: EvidenceLevel
    missing_element: str
    recommended_next_step: str
    source_ids: tuple[str, ...] = ()
    status: str = "OPEN"

    def __post_init__(self) -> None:
        object.__setattr__(self, "current_evidence", _tuple(self.current_evidence))
        object.__setattr__(self, "source_ids", _tuple(self.source_ids))
        object.__setattr__(self, "required_evidence", self.required_evidence if isinstance(self.required_evidence, EvidenceLevel) else EvidenceLevel(str(self.required_evidence)))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["current_evidence"] = list(self.current_evidence)
        data["source_ids"] = list(self.source_ids)
        data["required_evidence"] = self.required_evidence.value
        return data


@dataclass(frozen=True)
class NegativeResult:
    result_id: str
    statement: str
    status: str
    reason: str
    run_ids: tuple[str, ...] = ()
    conditions: dict[str, Any] = field(default_factory=dict)
    follow_up: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_ids", _tuple(self.run_ids))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["run_ids"] = list(self.run_ids)
        return data


@dataclass(frozen=True)
class TargetRecord:
    target_id: str
    gene_or_protein: str
    species: str
    source_id: str
    structure_id: str | None = None
    structure_source_id: str | None = None
    preparation_status: str = "NOT_PREPARED"

    def __post_init__(self) -> None:
        species = self.species.strip() or "UNKNOWN"
        object.__setattr__(self, "species", species)
        if not self.source_id.strip():
            raise ValueError("TargetRecord requires a source_id")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelFailureAnalysis:
    analysis_id: str
    model_id: str
    dataset_id: str
    split_id: str
    overall: dict[str, Any]
    segments: tuple[dict[str, Any], ...]
    notable_failures: tuple[dict[str, Any], ...]
    ood_policy: str
    uncertainty_policy: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "segments", tuple(dict(item) for item in self.segments))
        object.__setattr__(self, "notable_failures", tuple(dict(item) for item in self.notable_failures))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ModelFailureAnalysis":
        # ``to_dict`` exposes an aggregate row at the top level for report
        # consumers. Those convenience keys are derived from ``overall`` and
        # must not be passed back into the dataclass constructor on reload.
        payload = dict(value)
        for key in ("segment", "sample_count", "MAE", "RMSE", "OOD_fraction", "uncertainty_coverage"):
            payload.pop(key, None)
        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["segments"] = list(self.segments)
        data["notable_failures"] = list(self.notable_failures)
        # Keep the aggregate row query-friendly while retaining the richer
        # per-segment representation above. These names are intentionally
        # explicit because a report consumer must not confuse OOD fraction or
        # interval coverage with a confidence statement.
        data.update({
            "segment": "overall",
            "sample_count": self.overall.get("sample_count"),
            "MAE": self.overall.get("mae"),
            "RMSE": self.overall.get("rmse"),
            "OOD_fraction": self.overall.get("ood_fraction"),
            "uncertainty_coverage": self.overall.get("uncertainty_coverage"),
        })
        return data

    @property
    def segment(self) -> str:
        return "overall"

    @property
    def sample_count(self) -> int:
        return int(self.overall.get("sample_count") or 0)

    @property
    def MAE(self) -> float | None:
        return self.overall.get("mae")

    @property
    def RMSE(self) -> float | None:
        return self.overall.get("rmse")

    @property
    def bias(self) -> float | None:
        return self.overall.get("bias")

    @property
    def OOD_fraction(self) -> float | None:
        return self.overall.get("ood_fraction")


@dataclass(frozen=True)
class ResearchCampaignBundle:
    campaign_id: str
    bundle_id: str
    run_ids: tuple[str, ...]
    workflow_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    claim_ids: tuple[str, ...]
    report_path: str
    conclusion: str
    bundle_hash: str
    sealed: bool = True
    question_ids: tuple[str, ...] = ()
    research_question: str | None = None
    dataset_ids: tuple[str, ...] = ()
    model_ids: tuple[str, ...] = ()
    engine_ids: tuple[str, ...] = ()
    gap_ids: tuple[str, ...] = ()
    claim_targets: tuple[str, ...] = ()
    parent_campaign_id: str | None = None
    phase_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("run_ids", "workflow_ids", "source_ids", "evidence_ids", "claim_ids", "question_ids", "dataset_ids", "model_ids", "engine_ids", "gap_ids", "claim_targets"):
            object.__setattr__(self, name, _tuple(getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for name in ("run_ids", "workflow_ids", "source_ids", "evidence_ids", "claim_ids", "question_ids", "dataset_ids", "model_ids", "engine_ids", "gap_ids", "claim_targets"):
            data[name] = list(getattr(self, name))
        return data


@dataclass(frozen=True)
class ResearchCampaign:
    campaign_id: str
    title: str
    problem_id: str
    question: str
    status: CampaignStatus
    target: TargetRecord | None = None
    selected_sources: tuple[str, ...] = ()
    datasets: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    engines: tuple[str, ...] = ()
    workflow_ids: tuple[str, ...] = ()
    run_ids: tuple[str, ...] = ()
    bundle_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()
    gaps: tuple[ResearchGap, ...] = ()
    conflicts: tuple[SourceConflict, ...] = ()
    negative_results: tuple[NegativeResult, ...] = ()
    failure_analysis: ModelFailureAnalysis | None = None
    reproducibility: dict[str, Any] = field(default_factory=dict)
    report: dict[str, Any] = field(default_factory=dict)
    discovery_trace: dict[str, Any] = field(default_factory=dict)
    iteration: int = 0
    notes: tuple[str, ...] = ()
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    # Canonical campaign vocabulary from the 3.3 research contract. The
    # older selected_sources/datasets/models/engines names remain accepted for
    # persisted 3.2-compatible payloads and are synchronized below.
    domain: str = ""
    objective: str = ""
    hypothesis: str = ""
    research_questions: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    dataset_ids: tuple[str, ...] = ()
    model_ids: tuple[str, ...] = ()
    engine_requirements: tuple[str, ...] = ()
    evidence_target: EvidenceLevel | None = None
    max_iterations: int = 3
    max_runs: int = 4
    max_candidates: int = 50
    max_failures: int = 1
    safety_notes: tuple[str, ...] = ()
    claim_targets: tuple[str, ...] = ()
    completed_at: str | None = None
    parent_campaign_id: str | None = None
    phase_id: str = "PHASE-01"

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", self.status if isinstance(self.status, CampaignStatus) else CampaignStatus(str(self.status)))
        for name in ("selected_sources", "datasets", "models", "engines", "workflow_ids", "run_ids", "bundle_ids", "evidence_ids", "claim_ids", "notes"):
            object.__setattr__(self, name, _tuple(getattr(self, name)))
        for name in ("research_questions", "source_ids", "dataset_ids", "model_ids", "engine_requirements", "safety_notes", "claim_targets"):
            object.__setattr__(self, name, _tuple(getattr(self, name)))
        for canonical, legacy in (("source_ids", "selected_sources"), ("dataset_ids", "datasets"), ("model_ids", "models"), ("engine_requirements", "engines")):
            canonical_value = getattr(self, canonical)
            legacy_value = getattr(self, legacy)
            if not canonical_value and legacy_value:
                object.__setattr__(self, canonical, legacy_value)
            elif canonical_value and not legacy_value:
                object.__setattr__(self, legacy, canonical_value)
        if not self.research_questions:
            object.__setattr__(self, "research_questions", (self.question,))
        if not self.objective:
            object.__setattr__(self, "objective", self.question)
        if not self.domain:
            object.__setattr__(self, "domain", "general")
        if self.evidence_target is not None and not isinstance(self.evidence_target, EvidenceLevel):
            object.__setattr__(self, "evidence_target", EvidenceLevel(str(self.evidence_target)))
        for name in ("max_iterations", "max_runs", "max_candidates", "max_failures"):
            if int(getattr(self, name)) < 1:
                raise ValueError(f"{name} must be positive")
        object.__setattr__(self, "gaps", tuple(item if isinstance(item, ResearchGap) else ResearchGap(**item) for item in self.gaps))
        object.__setattr__(self, "conflicts", tuple(item if isinstance(item, SourceConflict) else SourceConflict(**item) for item in self.conflicts))
        object.__setattr__(self, "negative_results", tuple(item if isinstance(item, NegativeResult) else NegativeResult(**item) for item in self.negative_results))
        if self.target is not None and not isinstance(self.target, TargetRecord):
            object.__setattr__(self, "target", TargetRecord(**self.target))
        if self.failure_analysis is not None and not isinstance(self.failure_analysis, ModelFailureAnalysis):
            object.__setattr__(self, "failure_analysis", ModelFailureAnalysis.from_dict(self.failure_analysis))
        if not self.campaign_id.strip() or not self.problem_id.strip() or not self.question.strip():
            raise ValueError("ResearchCampaign requires campaign_id, problem_id and question")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["target"] = self.target.to_dict() if self.target else None
        for name in ("selected_sources", "datasets", "models", "engines", "workflow_ids", "run_ids", "bundle_ids", "evidence_ids", "claim_ids", "notes"):
            data[name] = list(getattr(self, name))
        for name in ("research_questions", "source_ids", "dataset_ids", "model_ids", "engine_requirements", "safety_notes", "claim_targets"):
            data[name] = list(getattr(self, name))
        if self.evidence_target is not None:
            data["evidence_target"] = self.evidence_target.value
        data["gaps"] = [item.to_dict() for item in self.gaps]
        data["conflicts"] = [item.to_dict() for item in self.conflicts]
        data["negative_results"] = [item.to_dict() for item in self.negative_results]
        data["failure_analysis"] = self.failure_analysis.to_dict() if self.failure_analysis else None
        return data

    @property
    def digest(self) -> str:
        return sha256_json(self.to_dict())


@dataclass(frozen=True)
class ProblemDiscoveryResult:
    candidates: tuple[ProblemCandidate, ...]
    primary_problem_ids: tuple[str, ...]
    secondary_problem_ids: tuple[str, ...]
    reasoning_summary: str
    audit: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(item if isinstance(item, ProblemCandidate) else ProblemCandidate(**item) for item in self.candidates))
        object.__setattr__(self, "primary_problem_ids", _tuple(self.primary_problem_ids))
        object.__setattr__(self, "secondary_problem_ids", _tuple(self.secondary_problem_ids))

    def to_dict(self) -> dict[str, Any]:
        return {"candidates": [item.to_dict() for item in self.candidates], "primary_problem_ids": list(self.primary_problem_ids), "secondary_problem_ids": list(self.secondary_problem_ids), "reasoning_summary": self.reasoning_summary, "audit": dict(self.audit)}


def new_campaign_id(problem_id: str) -> str:
    return f"CAM-{problem_id}-{uuid.uuid4().hex[:8].upper()}"
