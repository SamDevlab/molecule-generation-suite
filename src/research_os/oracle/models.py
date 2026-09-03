"""Typed question, plan, claim-gap and answer contracts for the Oracle."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from research_os.core.types import EvidenceLevel


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlanStatus(str, Enum):
    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    INVALID = "INVALID"
    INDETERMINATE = "INDETERMINATE"
    EXECUTED = "EXECUTED"


class OracleAnswerStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INDETERMINATE = "INDETERMINATE"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ResearchQuestion:
    text: str
    domain: str
    objective: str
    constraints: dict[str, Any] = field(default_factory=dict)
    required_evidence_level: EvidenceLevel = EvidenceLevel.E2_COMPUTATIONAL
    allowed_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    question_id: str = field(default_factory=lambda: f"Q-{uuid.uuid4().hex[:12].upper()}")
    created_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_evidence_level", self.required_evidence_level if isinstance(self.required_evidence_level, EvidenceLevel) else EvidenceLevel(str(self.required_evidence_level)))
        object.__setattr__(self, "allowed_tools", tuple(self.allowed_tools))
        object.__setattr__(self, "forbidden_tools", tuple(self.forbidden_tools))
        if not self.text.strip() or not self.domain.strip() or not self.objective.strip():
            raise ValueError("ResearchQuestion requires text, domain and objective")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["required_evidence_level"] = self.required_evidence_level.value
        data["allowed_tools"] = list(self.allowed_tools)
        data["forbidden_tools"] = list(self.forbidden_tools)
        return data


@dataclass(frozen=True)
class ClaimTarget:
    statement: str
    required_evidence_level: EvidenceLevel = EvidenceLevel.E2_COMPUTATIONAL
    claim_id: str = field(default_factory=lambda: f"CLM-TARGET-{uuid.uuid4().hex[:10].upper()}")

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_evidence_level", self.required_evidence_level if isinstance(self.required_evidence_level, EvidenceLevel) else EvidenceLevel(str(self.required_evidence_level)))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["required_evidence_level"] = self.required_evidence_level.value
        return data


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    lab: str
    experiment: str
    inputs: dict[str, Any] = field(default_factory=dict)
    requires: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    minimum_evidence_level: EvidenceLevel = EvidenceLevel.E0_HEURISTIC
    failure_policy: str = "STOP_DOWNSTREAM"

    def __post_init__(self) -> None:
        object.__setattr__(self, "requires", tuple(self.requires))
        object.__setattr__(self, "consumes", tuple(self.consumes))
        object.__setattr__(self, "produces", tuple(self.produces))
        object.__setattr__(self, "minimum_evidence_level", self.minimum_evidence_level if isinstance(self.minimum_evidence_level, EvidenceLevel) else EvidenceLevel(str(self.minimum_evidence_level)))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["requires"] = list(self.requires)
        data["consumes"] = list(self.consumes)
        data["produces"] = list(self.produces)
        data["minimum_evidence_level"] = self.minimum_evidence_level.value
        return data


@dataclass(frozen=True)
class ResearchPlan:
    question_id: str
    steps: tuple[PlanStep, ...]
    assumptions: tuple[str, ...] = ()
    required_sources: tuple[str, ...] = ()
    expected_outputs: tuple[str, ...] = ()
    risk_flags: tuple[str, ...] = ()
    claim_targets: tuple[ClaimTarget, ...] = ()
    status: PlanStatus = PlanStatus.PROPOSED
    plan_id: str = field(default_factory=lambda: f"PLAN-{uuid.uuid4().hex[:12].upper()}")
    created_at: str = field(default_factory=_now)
    rerun_of: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        object.__setattr__(self, "required_sources", tuple(self.required_sources))
        object.__setattr__(self, "expected_outputs", tuple(self.expected_outputs))
        object.__setattr__(self, "risk_flags", tuple(self.risk_flags))
        object.__setattr__(self, "claim_targets", tuple(self.claim_targets))
        object.__setattr__(self, "status", self.status if isinstance(self.status, PlanStatus) else PlanStatus(str(self.status)))

    def to_dict(self) -> dict[str, Any]:
        return {"plan_id": self.plan_id, "question_id": self.question_id, "created_at": self.created_at, "status": self.status.value, "rerun_of": self.rerun_of, "steps": [step.to_dict() for step in self.steps], "assumptions": list(self.assumptions), "required_sources": list(self.required_sources), "expected_outputs": list(self.expected_outputs), "risk_flags": list(self.risk_flags), "claim_targets": [target.to_dict() for target in self.claim_targets]}


@dataclass(frozen=True)
class ResearchGap:
    claim_id: str
    current_evidence: tuple[str, ...]
    required_evidence: EvidenceLevel
    missing_information: tuple[str, ...]
    recommended_next_steps: tuple[str, ...]
    gap_id: str = field(default_factory=lambda: f"GAP-{uuid.uuid4().hex[:12].upper()}")

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_evidence", self.required_evidence if isinstance(self.required_evidence, EvidenceLevel) else EvidenceLevel(str(self.required_evidence)))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["required_evidence"] = self.required_evidence.value
        for name in ("current_evidence", "missing_information", "recommended_next_steps"):
            data[name] = list(data[name])
        return data


@dataclass(frozen=True)
class OracleAnswer:
    status: OracleAnswerStatus
    summary: str
    claims: tuple[dict[str, Any], ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    limitations: tuple[str, ...] = ()
    conditions: dict[str, Any] = field(default_factory=dict)
    uncertainty: dict[str, Any] = field(default_factory=dict)
    first_loss: dict[str, Any] | None = None
    first_divergence: dict[str, Any] | None = None
    sources: tuple[str, ...] = ()
    datasets: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    run_ids: tuple[str, ...] = ()
    workflow_ids: tuple[str, ...] = ()
    bundle_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", self.status if isinstance(self.status, OracleAnswerStatus) else OracleAnswerStatus(str(self.status)))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        for name in ("claims", "evidence", "sources", "datasets", "models", "run_ids", "workflow_ids", "bundle_ids", "limitations"):
            data[name] = list(data[name])
        return data

