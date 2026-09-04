"""Auditable comparison of heterogeneous evidence without level inflation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
import uuid

from research_os.core.hashing import sha256_json
from research_os.core.types import EvidenceLevel


class EvidenceAgreementStatus(str, Enum):
    CONSISTENT = "CONSISTENT"
    PARTIALLY_CONSISTENT = "PARTIALLY_CONSISTENT"
    CONFLICTING = "CONFLICTING"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


def _value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


@dataclass(frozen=True)
class EvidenceAgreementAssessment:
    """Record whether evidence items agree under declared conditions.

    Agreement is descriptive.  It never adds evidence levels, turns a
    computational result into an experiment, or resolves a conflict by
    silently selecting the most convenient observation.
    """

    claim_target: str
    evidence_ids: tuple[str, ...]
    conditions: Mapping[str, Any]
    consistency: EvidenceAgreementStatus | str
    conflicts: tuple[str, ...] = ()
    strongest_supported_level: EvidenceLevel | str | None = None
    limitations: tuple[str, ...] = ()
    agreement_id: str = field(default_factory=lambda: f"AGR-{uuid.uuid4().hex[:12].upper()}")
    assessed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    digest: str | None = None
    # v3.6 names these fields explicitly.  They are appended after the v3.5
    # fields so positional construction from the previous contract remains
    # valid.
    assessment_id: str | None = None
    evidence_types: tuple[str, ...] = ()
    comparability: str = "NOT_ASSESSED"

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_target", str(self.claim_target))
        object.__setattr__(self, "evidence_ids", tuple(str(item) for item in self.evidence_ids))
        object.__setattr__(self, "conditions", dict(self.conditions or {}))
        object.__setattr__(self, "consistency", _value(self.consistency))
        object.__setattr__(self, "conflicts", tuple(str(item) for item in self.conflicts))
        object.__setattr__(self, "limitations", tuple(str(item) for item in self.limitations))
        object.__setattr__(self, "assessment_id", self.assessment_id or self.agreement_id)
        object.__setattr__(self, "evidence_types", tuple(str(item) for item in self.evidence_types))
        object.__setattr__(self, "comparability", str(self.comparability))
        if self.strongest_supported_level is not None:
            object.__setattr__(self, "strongest_supported_level", _value(self.strongest_supported_level))
        if self.consistency not in {item.value for item in EvidenceAgreementStatus}:
            raise ValueError(f"unknown evidence agreement status: {self.consistency}")
        if self.digest is None:
            object.__setattr__(self, "digest", sha256_json(self._hash_payload()))

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "claim_target": self.claim_target,
            "evidence_ids": self.evidence_ids,
            "conditions": self.conditions,
            "consistency": self.consistency,
            "conflicts": self.conflicts,
            "strongest_supported_level": self.strongest_supported_level,
            "limitations": self.limitations,
            "agreement_id": self.agreement_id,
            "assessed_at": self.assessed_at,
            "assessment_id": self.assessment_id,
            "evidence_types": self.evidence_types,
            "comparability": self.comparability,
        }

    @property
    def valid(self) -> bool:
        return self.digest == sha256_json(self._hash_payload())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update({
            "evidence_ids": list(self.evidence_ids),
            "conditions": dict(self.conditions),
            "consistency": self.consistency,
            "conflicts": list(self.conflicts),
            "strongest_supported_level": self.strongest_supported_level,
            "limitations": list(self.limitations),
            "assessment_id": self.assessment_id,
            "evidence_types": list(self.evidence_types),
            "comparability": self.comparability,
            "valid": self.valid,
        })
        return data
