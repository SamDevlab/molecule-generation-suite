"""Failure detectors for scientific decision benchmark invariants."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from research_os.decision.models import DecisionStatus, ScientificDecision


@dataclass(frozen=True)
class FalseSupportedDecision:
    decision_id: str
    flags: tuple[str, ...] = ()
    detected: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"decision_id": self.decision_id, "flags": list(self.flags), "detected": self.detected, "details": dict(self.details)}


@dataclass(frozen=True)
class FalseNoDecision:
    decision_id: str
    expected_status: str | None
    flags: tuple[str, ...] = ()
    detected: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"decision_id": self.decision_id, "expected_status": self.expected_status, "flags": list(self.flags), "detected": self.detected, "details": dict(self.details)}


def audit_false_supported_decision(decision: ScientificDecision, *, known_evidence_ids: set[str] | None = None, expected_invariants: tuple[str, ...] = (), case_ood: bool | None = None, uncertainty_relevant: bool = False, condition_mismatch: bool = False, source_conflict_ignored: bool = False, notes: tuple[str, ...] = ()) -> FalseSupportedDecision:
    flags: list[str] = []
    supported = decision.decision_status in {DecisionStatus.SUPPORTED_DECISION.value, DecisionStatus.PROVISIONAL_DECISION.value}
    if supported and ((case_ood and not decision.OOD_flags) or any("BYPASS" in item.upper() for item in decision.OOD_flags)):
        flags.append("OOD_IGNORED")
    if supported and uncertainty_relevant and not decision.uncertainties and not any(criterion.maximum_uncertainty_optional is not None for criterion in decision.criteria):
        flags.append("UNCERTAINTY_IGNORED")
    if supported and condition_mismatch:
        flags.append("CONDITION_MISMATCH")
    if supported and not decision.evidence_available:
        flags.append("MISSING_PROVENANCE")
    if supported and known_evidence_ids is not None and not set(decision.evidence_available).issubset(known_evidence_ids):
        flags.append("MISSING_PROVENANCE")
    if supported and any("single" in criterion.metric.lower() and "dock" in criterion.metric.lower() for criterion in decision.criteria):
        flags.append("SINGLE_DOCKING_SCORE_RANKING")
    if supported and any("experimental" in note.lower() and "simulation" in note.lower() for note in notes):
        flags.append("EXPERIMENTAL_INFERENCE_FROM_SIMULATION")
    if supported and source_conflict_ignored:
        flags.append("SOURCE_CONFLICT_IGNORED")
    if supported and not any(criterion.required for criterion in decision.criteria):
        flags.append("MISSING_REQUIRED_CRITERION")
    if supported and any(key in decision.conditions for key in ("total_score", "universal_score", "overall_score")):
        flags.append("UNIVERSAL_SCORE_CREATED")
    if supported and "EVIDENCE_CEILING_VIOLATED" in expected_invariants:
        flags.append("EVIDENCE_CEILING_VIOLATED")
    return FalseSupportedDecision(decision.decision_id, tuple(dict.fromkeys(flags)), bool(flags), {"expected_invariants": list(expected_invariants)})


def audit_false_no_decision(decision: ScientificDecision, *, expected_status: str | None, deterministic_available: bool = False) -> FalseNoDecision:
    flags: list[str] = []
    if expected_status in {DecisionStatus.SUPPORTED_DECISION.value, DecisionStatus.PROVISIONAL_DECISION.value} and decision.decision_status.startswith("NO_DECISION"):
        flags.append("KNOWN_SUPPORTED_CASE_REFUSED")
    if deterministic_available and decision.decision_status.startswith("NO_DECISION"):
        flags.append("AVAILABLE_DETERMINISTIC_RESULT_REFUSED")
    return FalseNoDecision(decision.decision_id, expected_status, tuple(flags), bool(flags), {"deterministic_available": deterministic_available})
