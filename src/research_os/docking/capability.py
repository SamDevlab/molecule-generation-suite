"""Bounded, machine-readable docking capability and claim boundary.

This module describes what the validated docking evidence supports.  It does
not validate a new docking run and it deliberately keeps capability status
separate from engine execution status.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping

from research_os.core.hashing import sha256_json
from research_os.core.types import EvidenceLevel, GateResult, GateStatus


class DockingContext(str, Enum):
    COGNATE_REDOCKING = "COGNATE_REDOCKING"
    NON_COGNATE_HOLO_CROSSDOCKING = "NON_COGNATE_HOLO_CROSSDOCKING"
    RIGID_APO_DOCKING = "RIGID_APO_DOCKING"
    UNKNOWN_DOCKING_CONTEXT = "UNKNOWN_DOCKING_CONTEXT"


class CapabilityClassification(str, Enum):
    VALIDATED_IN_DOMAIN = "VALIDATED_IN_DOMAIN"
    PARTIALLY_VALIDATED = "PARTIALLY_VALIDATED"
    INSUFFICIENTLY_VALIDATED = "INSUFFICIENTLY_VALIDATED"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"


PROFILE_ID_PREFIX = "research-os.docking.capability-profile.v1+"
PROFILE_SCHEMA = "research-os.docking.capability-profile.v1"
DEFAULT_PROFILE_PATH = Path(__file__).resolve().parents[3] / "configs" / "docking-capability-profile-v1.json"


@dataclass(frozen=True)
class CapabilityAssessment:
    context: DockingContext
    classification: CapabilityClassification
    evidence_level: EvidenceLevel
    execution_allowed: bool
    validation_sources: tuple[str, ...]
    known_limitations: tuple[str, ...]
    interpretation_boundary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "docking_context": self.context.value,
            "capability_status": self.classification.value,
            "evidence_level": self.evidence_level.value,
            "execution_allowed": self.execution_allowed,
            "validation_sources": list(self.validation_sources),
            "known_limitations": list(self.known_limitations),
            "interpretation_boundary": self.interpretation_boundary,
        }


@dataclass(frozen=True)
class DockingCapabilityProfile:
    data: Mapping[str, Any]
    profile_id: str
    profile_hash: str

    @property
    def evidence_level(self) -> EvidenceLevel:
        return EvidenceLevel(self.data["evidence_level"])

    @property
    def contexts(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.data.get("contexts", ()))

    def context_record(self, context: DockingContext | str) -> Mapping[str, Any]:
        normalized = normalize_context(context).value
        for record in self.contexts:
            if record.get("context_id") == normalized:
                return record
        raise KeyError(f"profile has no record for {normalized}")

    def assess(self, context: DockingContext | str) -> CapabilityAssessment:
        record = self.context_record(context)
        return CapabilityAssessment(
            context=DockingContext(record["context_id"]),
            classification=CapabilityClassification(record["classification"]),
            evidence_level=self.evidence_level,
            execution_allowed=bool(record.get("execution_allowed", False)),
            validation_sources=tuple(record.get("evidence_source_ids", ())),
            known_limitations=tuple(record.get("limitations", ())),
            interpretation_boundary=str(record["claim_boundary"]),
        )


def normalize_context(value: DockingContext | str | None) -> DockingContext:
    if isinstance(value, DockingContext):
        return value
    try:
        return DockingContext(str(value))
    except ValueError:
        return DockingContext.UNKNOWN_DOCKING_CONTEXT


def _scientific_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return the identity-bearing profile fields only.

    Operational metadata is intentionally excluded so timestamps, local paths,
    branch names, and CI details cannot change the scientific capability ID.
    """
    excluded = {"profile_id", "profile_hash", "operational_metadata"}
    return {key: value for key, value in data.items() if key not in excluded}


def profile_identity_from_mapping(data: Mapping[str, Any]) -> tuple[str, str]:
    profile_hash = sha256_json(_scientific_payload(data))
    return f"{PROFILE_ID_PREFIX}{profile_hash[:16]}", profile_hash


def load_profile(path: str | Path | None = None) -> DockingCapabilityProfile:
    profile_path = Path(path) if path is not None else DEFAULT_PROFILE_PATH
    with profile_path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    profile_id, profile_hash = profile_identity_from_mapping(data)
    declared_hash = data.get("profile_hash")
    declared_id = data.get("profile_id")
    if declared_hash is not None and declared_hash != profile_hash:
        raise ValueError("docking capability profile hash mismatch")
    if declared_id is not None and declared_id != profile_id:
        raise ValueError("docking capability profile ID mismatch")
    required = {"schema_version", "evidence_level", "evidence_sources", "contexts", "known_failure_modes", "interpretation_boundaries"}
    missing = sorted(required.difference(data))
    if missing:
        raise ValueError(f"docking capability profile missing fields: {', '.join(missing)}")
    return DockingCapabilityProfile(data=data, profile_id=profile_id, profile_hash=profile_hash)


def capability_metadata(context: DockingContext | str | None, profile: DockingCapabilityProfile | None = None) -> dict[str, Any]:
    active_profile = profile or load_profile()
    return {
        "capability_profile_id": active_profile.profile_id,
        "capability_profile_hash": active_profile.profile_hash,
        **active_profile.assess(normalize_context(context)).to_dict(),
    }


def capability_claim_gate(
    statement: str,
    *,
    docking_context: DockingContext | str | None,
    profile: DockingCapabilityProfile | None = None,
) -> GateResult:
    """Gate interpretive claims without blocking permitted engine execution."""
    from research_os.docking.claims import FORBIDDEN_DOCKING_CLAIM_TERMS

    active_profile = profile or load_profile()
    assessment = active_profile.assess(normalize_context(docking_context))
    lowered = str(statement).lower()
    forbidden = [term for term in FORBIDDEN_DOCKING_CLAIM_TERMS if term in lowered]
    if forbidden:
        return GateResult(
            "GATE-DOCKING-CAPABILITY-CLAIM",
            "DOCK-CAPABILITY-CLAIM-001",
            GateStatus.FAIL,
            "E2 docking evidence cannot support affinity, efficacy, safety, clinical, or experimental-truth claims",
            diagnostics={"forbidden_terms": forbidden, **assessment.to_dict()},
        )
    if assessment.classification in {CapabilityClassification.OUT_OF_DOMAIN, CapabilityClassification.INSUFFICIENTLY_VALIDATED}:
        return GateResult(
            "GATE-DOCKING-CAPABILITY-CLAIM",
            "DOCK-CAPABILITY-CLAIM-002",
            GateStatus.INSUFFICIENT_EVIDENCE,
            "docking context is outside the validated capability envelope; exploratory computational interpretation only",
            diagnostics=assessment.to_dict(),
        )
    return GateResult(
        "GATE-DOCKING-CAPABILITY-CLAIM",
        "DOCK-CAPABILITY-CLAIM-003",
        GateStatus.PASS,
        "claim is bounded to computational workflow behavior within the declared capability context",
        diagnostics=assessment.to_dict(),
    )


def classify_docking_context(context: DockingContext | str | None, profile: DockingCapabilityProfile | None = None) -> CapabilityClassification:
    return (profile or load_profile()).assess(normalize_context(context)).classification
