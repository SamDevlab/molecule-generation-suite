"""Typed, auditable outcome-impact contracts for Research OS v4.1.

This layer describes changes between registered scientific states. It does not
create Evidence, promote EvidenceLevels, or replace the Ledger.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping

from research_os.core.hashing import sha256_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ids(values: Iterable[Any] | None) -> tuple[str, ...]:
    return tuple(str(value) for value in (values or ()) if value is not None and str(value).strip())


class ImpactStatus(str, Enum):
    KNOWLEDGE_CHANGED = "KNOWLEDGE_CHANGED"
    DECISION_CHANGED = "DECISION_CHANGED"
    GAP_RESOLVED = "GAP_RESOLVED"
    GAP_REFINED = "GAP_REFINED"
    UNCERTAINTY_REDUCED = "UNCERTAINTY_REDUCED"
    NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"
    BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"


@dataclass(frozen=True)
class ResearchOutcomeImpact:
    """A before/after scientific impact trace for one bounded program."""

    impact_id: str
    program_id: str
    campaign_ids: tuple[str, ...]
    initial_question: str
    prior_state_summary: str
    prior_claim_ids: tuple[str, ...]
    prior_decision_ids: tuple[str, ...]
    prior_gap_ids: tuple[str, ...]
    new_source_ids: tuple[str, ...]
    new_dataset_ids: tuple[str, ...]
    new_run_ids: tuple[str, ...]
    new_evidence_ids: tuple[str, ...]
    new_claim_ids: tuple[str, ...]
    revised_claim_ids: tuple[str, ...]
    new_decision_ids: tuple[str, ...]
    revised_decision_ids: tuple[str, ...]
    resolved_gap_ids: tuple[str, ...]
    partially_resolved_gap_ids: tuple[str, ...]
    new_gap_ids: tuple[str, ...]
    uncertainty_changed: bool
    comparability_changed: bool
    actionable_next_step: str
    external_validation_required: bool
    impact_status: ImpactStatus | str
    summary: str
    digest: str | None = None
    created_at: str = field(default_factory=_now)

    _ID_FIELDS = (
        "campaign_ids", "prior_claim_ids", "prior_decision_ids", "prior_gap_ids",
        "new_source_ids", "new_dataset_ids", "new_run_ids", "new_evidence_ids",
        "new_claim_ids", "revised_claim_ids", "new_decision_ids",
        "revised_decision_ids", "resolved_gap_ids", "partially_resolved_gap_ids",
        "new_gap_ids",
    )

    def __post_init__(self) -> None:
        for name in self._ID_FIELDS:
            object.__setattr__(self, name, _ids(getattr(self, name)))
        if not self.impact_id.strip() or not self.program_id.strip():
            raise ValueError("ResearchOutcomeImpact requires impact_id and program_id")
        if not self.initial_question.strip() or not self.prior_state_summary.strip():
            raise ValueError("ResearchOutcomeImpact requires a question and prior state")
        if not self.actionable_next_step.strip() or not self.summary.strip():
            raise ValueError("ResearchOutcomeImpact requires an actionable next step and summary")
        status = self.impact_status if isinstance(self.impact_status, ImpactStatus) else ImpactStatus(str(self.impact_status))
        object.__setattr__(self, "impact_status", status)
        object.__setattr__(self, "uncertainty_changed", bool(self.uncertainty_changed))
        object.__setattr__(self, "comparability_changed", bool(self.comparability_changed))
        object.__setattr__(self, "external_validation_required", bool(self.external_validation_required))
        if self.digest is None:
            object.__setattr__(self, "digest", sha256_json(self._payload()))
        elif self.digest != sha256_json(self._payload()):
            raise ValueError("ResearchOutcomeImpact digest does not match its immutable payload")

    def _payload(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("digest", None)
        data["impact_status"] = self.impact_status.value
        for name in self._ID_FIELDS:
            data[name] = list(getattr(self, name))
        return data

    @property
    def valid(self) -> bool:
        return self.digest == sha256_json(self._payload())

    @property
    def has_material_change(self) -> bool:
        return self.impact_status != ImpactStatus.NO_MATERIAL_CHANGE

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResearchOutcomeImpact":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ProtocolSensitivityAssessment:
    """A declared, bounded comparison of legitimate protocol variants."""

    assessment_id: str
    campaign_id: str
    parameter: str
    baseline_value: Any
    alternate_values: tuple[Any, ...]
    run_ids: tuple[str, ...]
    metric: str
    result_variability: Mapping[str, Any]
    decision_changed: bool
    claim_changed: bool
    interpretation: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("alternate_values", "run_ids", "limitations"):
            object.__setattr__(self, name, tuple(getattr(self, name) or ()))
        object.__setattr__(self, "result_variability", dict(self.result_variability or {}))
        object.__setattr__(self, "decision_changed", bool(self.decision_changed))
        object.__setattr__(self, "claim_changed", bool(self.claim_changed))
        if not all(str(getattr(self, name)).strip() for name in ("assessment_id", "campaign_id", "parameter", "metric", "interpretation")):
            raise ValueError("ProtocolSensitivityAssessment requires identity, parameter, metric and interpretation")
        if not self.limitations:
            raise ValueError("protocol sensitivity limitations must be explicit")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["alternate_values"] = list(self.alternate_values)
        data["run_ids"] = list(self.run_ids)
        data["limitations"] = list(self.limitations)
        data["result_variability"] = dict(self.result_variability)
        return data


@dataclass(frozen=True)
class ConfidenceFailureCase:
    """A negative molecular ML case: low uncertainty but high observed error."""

    molecule: str
    prediction: float
    observed: float
    absolute_error: float
    uncertainty: float
    OOD_status: str
    scaffold: str
    source: str
    interpretation: str

    def __post_init__(self) -> None:
        calculated = abs(float(self.prediction) - float(self.observed))
        if abs(float(self.absolute_error) - calculated) > 1e-9:
            raise ValueError("ConfidenceFailureCase.absolute_error must equal |prediction-observed|")
        if float(self.uncertainty) < 0:
            raise ValueError("confidence failure uncertainty cannot be negative")
        if not all(str(getattr(self, name)).strip() for name in ("molecule", "OOD_status", "scaffold", "source", "interpretation")):
            raise ValueError("ConfidenceFailureCase requires molecule, domain status, scaffold, source and interpretation")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConditionDependentDecision:
    """Preserves two legitimate protocol results when a decision reverses."""

    decision_id: str
    protocol_a: str
    result_a: Any
    protocol_b: str
    result_b: Any
    changed: bool
    reason: str
    conditions: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "changed", bool(self.changed))
        object.__setattr__(self, "conditions", dict(self.conditions or {}))
        if not all(str(getattr(self, name)).strip() for name in ("decision_id", "protocol_a", "protocol_b", "reason")):
            raise ValueError("ConditionDependentDecision requires both protocol identities and a reason")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchOutcomeImpactStore:
    """Small append-only impact registry used by benchmarks and services."""

    _records: list[ResearchOutcomeImpact] = field(default_factory=list)

    def append(self, record: ResearchOutcomeImpact) -> ResearchOutcomeImpact:
        if not isinstance(record, ResearchOutcomeImpact):
            raise TypeError("impact store accepts ResearchOutcomeImpact records only")
        if any(item.impact_id == record.impact_id for item in self._records):
            raise ValueError(f"impact_id already exists and history is append-only: {record.impact_id}")
        if not record.valid:
            raise ValueError("cannot append an invalid ResearchOutcomeImpact")
        self._records.append(record)
        return record

    def list(self) -> tuple[ResearchOutcomeImpact, ...]:
        return tuple(self._records)

    def to_dict(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self._records]


__all__ = ["ConfidenceFailureCase", "ConditionDependentDecision", "ImpactStatus", "ProtocolSensitivityAssessment", "ResearchOutcomeImpact", "ResearchOutcomeImpactStore"]
