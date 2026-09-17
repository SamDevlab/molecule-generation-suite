"""Typed, auditable contracts for cross-domain scientific decisions.

The models deliberately keep molecular properties, solubility, applicability
domain, uncertainty, and docking variability as separate dimensions.  There
is no aggregate score in this module and no field that can be interpreted as a
universal scientific ranking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import sqrt
from statistics import fmean, pstdev
from typing import Any, Mapping, Sequence
import uuid

from research_os.core.hashing import sha256_json
from research_os.core.types import EvidenceLevel


def _value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _tuple(values: Sequence[Any] | None) -> tuple[Any, ...]:
    return tuple(values or ())


class DecisionStatus(str, Enum):
    SUPPORTED_DECISION = "SUPPORTED_DECISION"
    PROVISIONAL_DECISION = "PROVISIONAL_DECISION"
    NO_DECISION_INSUFFICIENT_EVIDENCE = "NO_DECISION_INSUFFICIENT_EVIDENCE"
    NO_DECISION_CONFLICTING_EVIDENCE = "NO_DECISION_CONFLICTING_EVIDENCE"
    NO_DECISION_OUT_OF_DOMAIN = "NO_DECISION_OUT_OF_DOMAIN"
    REJECTED_DECISION_REQUEST = "REJECTED_DECISION_REQUEST"


class DockingSeparationStatus(str, Enum):
    CLEARLY_SEPARATED_UNDER_PROTOCOL = "CLEARLY_SEPARATED_UNDER_PROTOCOL"
    POSSIBLY_SEPARATED = "POSSIBLY_SEPARATED"
    WITHIN_PROTOCOL_VARIABILITY = "WITHIN_PROTOCOL_VARIABILITY"
    INSUFFICIENT_REPLICATES = "INSUFFICIENT_REPLICATES"
    NOT_COMPARABLE = "NOT_COMPARABLE"


@dataclass(frozen=True)
class DecisionCriterion:
    criterion_id: str
    metric: str
    direction: str
    required: bool
    weight_optional: float | None = None
    minimum_evidence_level: EvidenceLevel | str | None = None
    maximum_uncertainty_optional: float | None = None
    OOD_policy: str = "RETAIN_AND_DO_NOT_RANK"
    conditions: Mapping[str, Any] = field(default_factory=dict)
    comparison_protocol: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "criterion_id", str(self.criterion_id))
        object.__setattr__(self, "metric", str(self.metric))
        object.__setattr__(self, "direction", str(self.direction).lower())
        object.__setattr__(self, "conditions", dict(self.conditions or {}))
        if self.minimum_evidence_level is not None:
            object.__setattr__(self, "minimum_evidence_level", _value(self.minimum_evidence_level))
        if self.weight_optional is not None and self.weight_optional < 0:
            raise ValueError("optional criterion weights cannot be negative")
        if self.maximum_uncertainty_optional is not None and self.maximum_uncertainty_optional < 0:
            raise ValueError("maximum uncertainty cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "metric": self.metric,
            "direction": self.direction,
            "required": self.required,
            "weight_optional": self.weight_optional,
            "minimum_evidence_level": self.minimum_evidence_level,
            "maximum_uncertainty_optional": self.maximum_uncertainty_optional,
            "OOD_policy": self.OOD_policy,
            "conditions": dict(self.conditions),
            "comparison_protocol": self.comparison_protocol,
        }


@dataclass(frozen=True)
class ScientificDecision:
    decision_id: str
    campaign_id: str
    question_id: str
    decision_question: str
    options: tuple[str, ...]
    criteria: tuple[DecisionCriterion, ...]
    required_evidence: tuple[str, ...]
    evidence_available: tuple[str, ...]
    supporting_claim_ids: tuple[str, ...]
    conflicting_claim_ids: tuple[str, ...]
    conditions: Mapping[str, Any]
    uncertainties: tuple[str, ...]
    OOD_flags: tuple[str, ...]
    selected_option: str | None
    rejected_options: tuple[str, ...]
    decision_status: DecisionStatus | str
    rationale_summary: str
    limitations: tuple[str, ...]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", str(self.decision_id))
        object.__setattr__(self, "campaign_id", str(self.campaign_id))
        object.__setattr__(self, "question_id", str(self.question_id))
        for name in ("options", "required_evidence", "evidence_available", "supporting_claim_ids", "conflicting_claim_ids", "uncertainties", "OOD_flags", "rejected_options", "limitations"):
            object.__setattr__(self, name, tuple(str(item) for item in getattr(self, name)))
        object.__setattr__(self, "criteria", tuple(self.criteria))
        object.__setattr__(self, "conditions", dict(self.conditions or {}))
        forbidden = {"total_score", "universal_score", "overall_score"}
        if forbidden & set(self.conditions):
            raise ValueError("ScientificDecision cannot contain a universal or total score")
        object.__setattr__(self, "decision_status", _value(self.decision_status))
        if self.selected_option is not None:
            object.__setattr__(self, "selected_option", str(self.selected_option))
        if self.selected_option is not None and self.selected_option not in self.options:
            raise ValueError("selected_option must be one of options")
        if self.decision_status in {DecisionStatus.SUPPORTED_DECISION.value, DecisionStatus.PROVISIONAL_DECISION.value} and self.selected_option is None:
            raise ValueError("a supported or provisional decision requires selected_option")
        if self.decision_status not in {item.value for item in DecisionStatus}:
            raise ValueError(f"unknown decision status: {self.decision_status}")

    @property
    def has_hidden_score(self) -> bool:
        return False

    @property
    def digest(self) -> str:
        return sha256_json(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "campaign_id": self.campaign_id,
            "question_id": self.question_id,
            "decision_question": self.decision_question,
            "options": list(self.options),
            "criteria": [criterion.to_dict() for criterion in self.criteria],
            "required_evidence": list(self.required_evidence),
            "evidence_available": list(self.evidence_available),
            "supporting_claim_ids": list(self.supporting_claim_ids),
            "conflicting_claim_ids": list(self.conflicting_claim_ids),
            "conditions": dict(self.conditions),
            "uncertainties": list(self.uncertainties),
            "OOD_flags": list(self.OOD_flags),
            "selected_option": self.selected_option,
            "rejected_options": list(self.rejected_options),
            "decision_status": self.decision_status,
            "rationale_summary": self.rationale_summary,
            "limitations": list(self.limitations),
            "created_at": self.created_at,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificDecision":
        criteria = tuple(DecisionCriterion(**dict(item)) for item in payload.get("criteria", ()))
        fields = dict(payload)
        fields.pop("digest", None)
        fields["criteria"] = criteria
        return cls(**fields)


@dataclass(frozen=True)
class DockingProtocolVariability:
    protocol_id: str
    replicate_run_ids: tuple[str, ...]
    score_mean: float
    score_std: float
    score_range: tuple[float, float]
    replicate_count: int
    interpretation: str
    decision_relevance: str
    replicate_scores: tuple[float, ...] = ()

    @classmethod
    def from_scores(cls, protocol_id: str, replicate_run_ids: Sequence[str], scores: Sequence[float], *, decision_relevance: str) -> "DockingProtocolVariability":
        values = tuple(float(value) for value in scores)
        run_ids = tuple(str(value) for value in replicate_run_ids)
        if not values or len(values) != len(run_ids):
            raise ValueError("docking variability requires one score per replicate run")
        if len(values) > 3:
            raise ValueError("v3.6 docking variability is limited to three replicates")
        mean = float(fmean(values))
        std = float(pstdev(values)) if len(values) > 1 else 0.0
        return cls(str(protocol_id), run_ids, mean, std, (min(values), max(values)), len(values), "Three-replicate protocol spread; no formal distribution or significance inference.", str(decision_relevance), values)

    def __post_init__(self) -> None:
        object.__setattr__(self, "replicate_run_ids", tuple(str(item) for item in self.replicate_run_ids))
        object.__setattr__(self, "replicate_scores", tuple(float(item) for item in self.replicate_scores))
        object.__setattr__(self, "score_range", tuple(float(item) for item in self.score_range))
        if self.replicate_count != len(self.replicate_run_ids):
            raise ValueError("replicate_count must match replicate_run_ids")
        if self.replicate_scores and len(self.replicate_scores) != self.replicate_count:
            raise ValueError("replicate_scores must match replicate_count")
        if len(self.score_range) != 2:
            raise ValueError("score_range must contain min and max")

    @property
    def score_min(self) -> float:
        return float(self.score_range[0])

    @property
    def score_max(self) -> float:
        return float(self.score_range[1])

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "replicate_run_ids": list(self.replicate_run_ids),
            "score_mean": self.score_mean,
            "score_std": self.score_std,
            "score_range": list(self.score_range),
            "score_min": self.score_min,
            "score_max": self.score_max,
            "replicate_count": self.replicate_count,
            "interpretation": self.interpretation,
            "decision_relevance": self.decision_relevance,
            "replicate_scores": list(self.replicate_scores),
        }


@dataclass(frozen=True)
class DockingSeparationAssessment:
    option_a: str
    option_b: str
    protocol_id: str
    mean_difference_kcal_mol: float
    variability_margin_kcal_mol: float
    status: DockingSeparationStatus | str
    rationale: str
    comparable: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", _value(self.status))
        if self.status not in {item.value for item in DockingSeparationStatus}:
            raise ValueError(f"unknown docking separation status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return {"option_a": self.option_a, "option_b": self.option_b, "protocol_id": self.protocol_id, "mean_difference_kcal_mol": self.mean_difference_kcal_mol, "variability_margin_kcal_mol": self.variability_margin_kcal_mol, "status": self.status, "rationale": self.rationale, "comparable": self.comparable}


def evaluate_docking_separation(left: DockingProtocolVariability, right: DockingProtocolVariability, *, option_a: str = "A", option_b: str = "B", clear_margin_kcal_mol: float = 1.0) -> DockingSeparationAssessment:
    if left.protocol_id != right.protocol_id or left.decision_relevance != right.decision_relevance:
        return DockingSeparationAssessment(option_a, option_b, left.protocol_id, abs(left.score_mean - right.score_mean), float("nan"), DockingSeparationStatus.NOT_COMPARABLE, "Protocol identity or decision relevance does not match; no score comparison was made.", False)
    if left.replicate_count < 3 or right.replicate_count < 3:
        return DockingSeparationAssessment(option_a, option_b, left.protocol_id, abs(left.score_mean - right.score_mean), max(left.score_std, right.score_std), DockingSeparationStatus.INSUFFICIENT_REPLICATES, "The declared guard requires three replicates per option.")
    difference = abs(left.score_mean - right.score_mean)
    spread = max(left.score_max - left.score_min, right.score_max - right.score_min, left.score_std + right.score_std)
    if difference <= max(spread, 0.25):
        status = DockingSeparationStatus.WITHIN_PROTOCOL_VARIABILITY
        rationale = "The mean difference is no larger than the observed three-replicate protocol spread."
    elif difference >= max(clear_margin_kcal_mol, 2.0 * spread):
        status = DockingSeparationStatus.CLEARLY_SEPARATED_UNDER_PROTOCOL
        rationale = "The mean difference exceeds the declared protocol-margin guard; this is not a formal significance test."
    else:
        status = DockingSeparationStatus.POSSIBLY_SEPARATED
        rationale = "The means differ, but the observed protocol spread does not support a clear separation."
    return DockingSeparationAssessment(option_a, option_b, left.protocol_id, difference, spread, status, rationale)


@dataclass(frozen=True)
class SimulationExperimentComparison:
    comparison_id: str
    simulated_evidence_ids: tuple[str, ...]
    experimental_evidence_ids: tuple[str, ...]
    metric: str
    condition_match: str
    simulation_value: float | None
    experimental_value: float | None
    uncertainty: float | None
    absolute_difference: float | None
    relative_difference: float | None
    tolerance_protocol: str
    status: str

    @classmethod
    def from_values(cls, *, metric: str, simulated_evidence_ids: Sequence[str], experimental_evidence_ids: Sequence[str], condition_match: str, simulation_value: float | None, experimental_value: float | None, uncertainty: float | None, tolerance_protocol: str, absolute_tolerance: float | None = None, relative_tolerance: float | None = None, comparison_id: str | None = None) -> "SimulationExperimentComparison":
        if not condition_match or condition_match.upper() in {"UNKNOWN", "INCOMPATIBLE", "NOT_COMPARABLE"}:
            status = SimulationExperimentStatus.INSUFFICIENT_METADATA if condition_match.upper() == "UNKNOWN" else SimulationExperimentStatus.NOT_COMPARABLE
            return cls(comparison_id or f"CMP-{uuid.uuid4().hex[:12].upper()}", tuple(simulated_evidence_ids), tuple(experimental_evidence_ids), metric, condition_match, simulation_value, experimental_value, uncertainty, None, None, tolerance_protocol, status.value)
        if simulation_value is None or experimental_value is None:
            return cls(comparison_id or f"CMP-{uuid.uuid4().hex[:12].upper()}", tuple(simulated_evidence_ids), tuple(experimental_evidence_ids), metric, condition_match, simulation_value, experimental_value, uncertainty, None, None, tolerance_protocol, SimulationExperimentStatus.INSUFFICIENT_METADATA.value)
        absolute = abs(float(simulation_value) - float(experimental_value))
        relative = absolute / abs(float(experimental_value)) if experimental_value else None
        within_absolute = absolute_tolerance is not None and absolute <= absolute_tolerance
        within_relative = relative_tolerance is not None and relative is not None and relative <= relative_tolerance
        status = SimulationExperimentStatus.AGREES_WITHIN_PROTOCOL if within_absolute or within_relative else SimulationExperimentStatus.DISAGREES
        return cls(comparison_id or f"CMP-{uuid.uuid4().hex[:12].upper()}", tuple(simulated_evidence_ids), tuple(experimental_evidence_ids), metric, condition_match, float(simulation_value), float(experimental_value), uncertainty, absolute, relative, tolerance_protocol, status.value)

    def __post_init__(self) -> None:
        object.__setattr__(self, "simulated_evidence_ids", tuple(str(item) for item in self.simulated_evidence_ids))
        object.__setattr__(self, "experimental_evidence_ids", tuple(str(item) for item in self.experimental_evidence_ids))
        object.__setattr__(self, "status", _value(self.status))
        if self.status not in {item.value for item in SimulationExperimentStatus}:
            raise ValueError(f"unknown simulation-experiment status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return {"comparison_id": self.comparison_id, "simulated_evidence_ids": list(self.simulated_evidence_ids), "experimental_evidence_ids": list(self.experimental_evidence_ids), "metric": self.metric, "condition_match": self.condition_match, "simulation_value": self.simulation_value, "experimental_value": self.experimental_value, "uncertainty": self.uncertainty, "absolute_difference": self.absolute_difference, "relative_difference": self.relative_difference, "tolerance_protocol": self.tolerance_protocol, "status": self.status}


class SimulationExperimentStatus(str, Enum):
    AGREES_WITHIN_PROTOCOL = "AGREES_WITHIN_PROTOCOL"
    DISAGREES = "DISAGREES"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    INSUFFICIENT_METADATA = "INSUFFICIENT_METADATA"


@dataclass(frozen=True)
class BatteryDatasetQualityAssessment:
    dataset_id: str
    observed_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    status: str
    limitations: tuple[str, ...] = ()
    assessment_id: str = field(default_factory=lambda: f"BATQ-{uuid.uuid4().hex[:12].upper()}")

    def __post_init__(self) -> None:
        for name in ("observed_fields", "missing_fields", "evidence_ids", "limitations"):
            object.__setattr__(self, name, tuple(str(item) for item in getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return {"assessment_id": self.assessment_id, "dataset_id": self.dataset_id, "observed_fields": list(self.observed_fields), "missing_fields": list(self.missing_fields), "evidence_ids": list(self.evidence_ids), "status": self.status, "limitations": list(self.limitations)}


class BatteryProtocolMatchStatus(str, Enum):
    MATCH = "MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BatteryProtocolComparability:
    comparison_id: str
    source_a: str
    source_b: str
    matched_fields: tuple[str, ...]
    mismatched_fields: tuple[str, ...]
    status: BatteryProtocolMatchStatus | str
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "matched_fields", tuple(str(item) for item in self.matched_fields))
        object.__setattr__(self, "mismatched_fields", tuple(str(item) for item in self.mismatched_fields))
        object.__setattr__(self, "limitations", tuple(str(item) for item in self.limitations))
        object.__setattr__(self, "status", _value(self.status))
        if self.status not in {item.value for item in BatteryProtocolMatchStatus}:
            raise ValueError(f"unknown battery protocol status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return {"comparison_id": self.comparison_id, "source_a": self.source_a, "source_b": self.source_b, "matched_fields": list(self.matched_fields), "mismatched_fields": list(self.mismatched_fields), "status": self.status, "limitations": list(self.limitations)}


@dataclass(frozen=True)
class PlanParsimonyAssessment:
    plan_id: str
    required_steps: tuple[str, ...]
    optional_steps: tuple[str, ...]
    redundant_steps: tuple[str, ...]
    unsupported_steps: tuple[str, ...]
    minimal_sufficient: bool
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("required_steps", "optional_steps", "redundant_steps", "unsupported_steps", "notes"):
            object.__setattr__(self, name, tuple(str(item) for item in getattr(self, name)))
        if self.minimal_sufficient and self.unsupported_steps:
            raise ValueError("a plan with unsupported required work cannot be minimal_sufficient")

    def to_dict(self) -> dict[str, Any]:
        return {"plan_id": self.plan_id, "required_steps": list(self.required_steps), "optional_steps": list(self.optional_steps), "redundant_steps": list(self.redundant_steps), "unsupported_steps": list(self.unsupported_steps), "minimal_sufficient": self.minimal_sufficient, "notes": list(self.notes)}
