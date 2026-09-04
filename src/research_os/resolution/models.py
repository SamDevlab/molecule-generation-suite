"""Typed records used when a scientific gap is attempted and evaluated.

These records are deliberately conservative.  They can describe a failed
retrieval or an incomplete observation, but they do not turn missing fields
into values and they never raise an evidence level by themselves.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import builtins
import math
from typing import Any, Mapping
import uuid

from research_os.core.hashing import sha256_json
from research_os.core.types import EvidenceLevel


UNKNOWN = "UNKNOWN"
_UNKNOWN_VALUES = {"", "UNKNOWN", "NOT_REPORTED", "NOT_AVAILABLE", "N/A", "NA", "NULL", "NONE"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    return tuple(str(item) for item in (value or ()) if item is not None and str(item))


def _unknown(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip().upper() in _UNKNOWN_VALUES)


def _canonical(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.strip().upper().split())
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


class ResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    BLOCKED = "BLOCKED"
    INVALIDATED = "INVALIDATED"


class ConditionMatchStatus(str, Enum):
    MATCH = "MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ConditionMatchResult:
    status: ConditionMatchStatus
    compared_fields: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    mismatches: dict[str, dict[str, Any]] = field(default_factory=dict)
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", self.status if isinstance(self.status, ConditionMatchStatus) else ConditionMatchStatus(str(self.status)))
        object.__setattr__(self, "compared_fields", _tuple(self.compared_fields))
        object.__setattr__(self, "missing_fields", _tuple(self.missing_fields))
        object.__setattr__(self, "mismatches", {str(key): dict(value) for key, value in (self.mismatches or {}).items()})

    @property
    def comparable(self) -> bool:
        """Only a complete match is safe for a condition-matched comparison."""
        return self.status is ConditionMatchStatus.MATCH

    def require_comparable(self) -> None:
        if not self.comparable:
            raise ValueError(f"condition comparison is not defensible: {self.status.value}")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["compared_fields"] = list(self.compared_fields)
        data["missing_fields"] = list(self.missing_fields)
        return {**data, "comparable": self.comparable}


class ConditionMatcher:
    """Compare declared fields without silently imputing absent conditions."""

    @staticmethod
    def match(left: Mapping[str, Any], right: Mapping[str, Any], required_fields: tuple[str, ...] | list[str] | None = None) -> ConditionMatchResult:
        fields = tuple(required_fields or sorted(set(left) | set(right)))
        compared: list[str] = []
        missing: list[str] = []
        mismatches: dict[str, dict[str, Any]] = {}
        for name in fields:
            a, b = left.get(name), right.get(name)
            if _unknown(a) or _unknown(b):
                missing.append(name)
            elif _canonical(a) == _canonical(b):
                compared.append(name)
            else:
                mismatches[name] = {"left": a, "right": b}
        if mismatches:
            status = ConditionMatchStatus.INCOMPATIBLE
            reason = "known condition fields disagree; the observations must not be compared as matched"
        elif not compared:
            status = ConditionMatchStatus.UNKNOWN
            reason = "no required condition field is known on both observations"
        elif missing:
            status = ConditionMatchStatus.PARTIAL_MATCH
            reason = "some fields match, but missing fields prevent a complete condition-matched comparison"
        else:
            status = ConditionMatchStatus.MATCH
            reason = "all required condition fields are known and equal"
        return ConditionMatchResult(status, tuple(compared), tuple(missing), mismatches, reason)


@dataclass(frozen=True)
class MaterialObservation:
    """One source-located materials observation, including explicit unknowns."""

    observation_id: str
    material: str
    composition: Any = UNKNOWN
    processing: Any = UNKNOWN
    microstructure: Any = UNKNOWN
    environment: Any = UNKNOWN
    temperature: Any = UNKNOWN
    pressure: Any = UNKNOWN
    stress: Any = UNKNOWN
    method: Any = UNKNOWN
    property: str = UNKNOWN
    value: Any = None
    unit: str = UNKNOWN
    uncertainty: Any = UNKNOWN
    source_id: str = UNKNOWN
    locator: str = UNKNOWN
    evidence_level: EvidenceLevel | str = EvidenceLevel.E0_HEURISTIC

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_level", self.evidence_level if isinstance(self.evidence_level, EvidenceLevel) else EvidenceLevel(str(self.evidence_level)))
        object.__setattr__(self, "material", str(self.material or UNKNOWN))
        object.__setattr__(self, "property", str(self.property or UNKNOWN))
        object.__setattr__(self, "unit", str(self.unit or UNKNOWN))
        object.__setattr__(self, "source_id", str(self.source_id or UNKNOWN))
        object.__setattr__(self, "locator", str(self.locator or UNKNOWN))

    @builtins.property
    def condition_fields(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in ("material", "composition", "processing", "microstructure", "environment", "temperature", "pressure", "stress", "method")}

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_level"] = self.evidence_level.value
        data["condition_fields"] = self.condition_fields
        return data

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, observation_id: str | None = None) -> "MaterialObservation":
        payload = dict(raw)
        payload.setdefault("observation_id", observation_id or f"MAT-OBS-{uuid.uuid4().hex[:12].upper()}")
        return cls(**payload)


@dataclass(frozen=True)
class ElectrochemicalObservation:
    """Normalized battery observation; absent measurements remain unknown."""

    observation_id: str
    dataset_id: str
    source_id: str
    cell_id: Any = UNKNOWN
    cycle_index: Any = UNKNOWN
    operation: Any = UNKNOWN
    temperature_c: Any = None
    current_a: Any = None
    voltage_v: Any = None
    capacity_ah: Any = None
    resistance_ohm: Any = None
    time_s: Any = None
    units: dict[str, str] = field(default_factory=dict)
    conditions: dict[str, Any] = field(default_factory=dict)
    method: str = UNKNOWN
    locator: str = UNKNOWN
    evidence_level: EvidenceLevel | str = EvidenceLevel.E0_HEURISTIC

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_level", self.evidence_level if isinstance(self.evidence_level, EvidenceLevel) else EvidenceLevel(str(self.evidence_level)))
        object.__setattr__(self, "units", {str(key): str(value) for key, value in (self.units or {}).items()})
        object.__setattr__(self, "conditions", dict(self.conditions or {}))

    @property
    def complete_condition_fields(self) -> tuple[str, ...]:
        required = ("cell_id", "cycle_index", "operation", "temperature_c", "current_a", "voltage_v", "capacity_ah", "time_s")
        return tuple(name for name in required if not _unknown(getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_level"] = self.evidence_level.value
        data["complete_condition_fields"] = list(self.complete_condition_fields)
        return data


@dataclass(frozen=True)
class PublicDatasetArtifact:
    dataset_id: str
    title: str
    source_id: str
    source_url: str
    license: str
    retrieved_at: str
    retrieval_status: str
    artifact_path: str | None = None
    artifact_sha256: str | None = None
    artifact_size_bytes: int | None = None
    schema: dict[str, Any] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    conditions: dict[str, Any] = field(default_factory=dict)
    provenance: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", _tuple(self.provenance))
        object.__setattr__(self, "notes", _tuple(self.notes))
        object.__setattr__(self, "schema", dict(self.schema or {}))
        object.__setattr__(self, "units", dict(self.units or {}))
        object.__setattr__(self, "conditions", dict(self.conditions or {}))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["provenance"] = list(self.provenance)
        data["notes"] = list(self.notes)
        # Dataset bundle verification uses the canonical ``sha256`` key;
        # retain the descriptive alias as well for human-facing reports.
        data["sha256"] = self.artifact_sha256
        return data


@dataclass(frozen=True)
class BatteryDatasetAssessment:
    dataset_id: str
    artifact: PublicDatasetArtifact
    observation_ids: tuple[str, ...] = ()
    evidence_level: EvidenceLevel | str = EvidenceLevel.E0_HEURISTIC
    status: str = "INSUFFICIENT_EVIDENCE"
    analysis: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    assessment_hash: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_ids", _tuple(self.observation_ids))
        object.__setattr__(self, "evidence_level", self.evidence_level if isinstance(self.evidence_level, EvidenceLevel) else EvidenceLevel(str(self.evidence_level)))
        object.__setattr__(self, "notes", _tuple(self.notes))
        object.__setattr__(self, "analysis", dict(self.analysis or {}))
        if self.assessment_hash is None:
            object.__setattr__(self, "assessment_hash", sha256_json(self._hash_payload()))

    def _hash_payload(self) -> dict[str, Any]:
        return {"dataset_id": self.dataset_id, "artifact": self.artifact.to_dict(), "observation_ids": self.observation_ids, "evidence_level": self.evidence_level.value, "status": self.status, "analysis": self.analysis, "notes": self.notes}

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_payload(), "artifact": self.artifact.to_dict(), "observation_ids": list(self.observation_ids), "notes": list(self.notes), "assessment_hash": self.assessment_hash}


@dataclass(frozen=True)
class ExternalValidationAssessment:
    dataset_id: str
    source_ids: tuple[str, ...]
    model_id: str
    frozen_protocol: str
    overlap_count: int | None
    training_count: int | None
    external_count: int | None
    schema_compatible: bool | None
    license_status: str
    status: str
    promotion_decision: str
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_ids", _tuple(self.source_ids))
        object.__setattr__(self, "notes", _tuple(self.notes))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_ids"] = list(self.source_ids)
        data["notes"] = list(self.notes)
        return data


@dataclass(frozen=True)
class DockingReproducibilityAssessment:
    campaign_id: str
    run_ids: tuple[str, ...]
    seeds: tuple[int, ...]
    scores_kcal_mol: tuple[float, ...]
    same_protocol: bool
    status: str
    evidence_level: EvidenceLevel | str = EvidenceLevel.E2_COMPUTATIONAL
    score_spread_kcal_mol: float | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_ids", _tuple(self.run_ids))
        object.__setattr__(self, "seeds", tuple(int(item) for item in self.seeds))
        object.__setattr__(self, "scores_kcal_mol", tuple(float(item) for item in self.scores_kcal_mol))
        object.__setattr__(self, "evidence_level", self.evidence_level if isinstance(self.evidence_level, EvidenceLevel) else EvidenceLevel(str(self.evidence_level)))
        object.__setattr__(self, "notes", _tuple(self.notes))

    @property
    def reproducible(self) -> bool:
        return self.status == "REPRODUCED" and len(self.run_ids) >= 3 and self.same_protocol

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update({"run_ids": list(self.run_ids), "seeds": list(self.seeds), "scores_kcal_mol": list(self.scores_kcal_mol), "notes": list(self.notes), "evidence_level": self.evidence_level.value, "reproducible": self.reproducible})
        return data


@dataclass(frozen=True)
class GapResolution:
    """One append-only attempt to reduce a named ResearchGap."""

    resolution_id: str
    gap_id: str
    attempted_at: str
    strategy: str
    source_ids: tuple[str, ...]
    dataset_ids: tuple[str, ...]
    engine_ids: tuple[str, ...]
    run_ids: tuple[str, ...]
    evidence_before: tuple[str, ...]
    evidence_after: tuple[str, ...]
    status: ResolutionStatus | str
    remaining_gap: str
    campaign_id: str | None = None
    plan: dict[str, Any] = field(default_factory=dict)
    assessments: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", self.status if isinstance(self.status, ResolutionStatus) else ResolutionStatus(str(self.status)))
        for name in ("source_ids", "dataset_ids", "engine_ids", "run_ids", "evidence_before", "evidence_after", "notes"):
            object.__setattr__(self, name, _tuple(getattr(self, name)))
        object.__setattr__(self, "plan", dict(self.plan or {}))
        object.__setattr__(self, "assessments", dict(self.assessments or {}))
        if not self.resolution_id.strip() or not self.gap_id.strip() or not self.strategy.strip():
            raise ValueError("GapResolution requires resolution_id, gap_id and strategy")
        if self.digest is None:
            object.__setattr__(self, "digest", sha256_json(self._hash_payload()))

    def _hash_payload(self) -> dict[str, Any]:
        return {"resolution_id": self.resolution_id, "gap_id": self.gap_id, "attempted_at": self.attempted_at, "strategy": self.strategy, "source_ids": self.source_ids, "dataset_ids": self.dataset_ids, "engine_ids": self.engine_ids, "run_ids": self.run_ids, "evidence_before": self.evidence_before, "evidence_after": self.evidence_after, "status": self.status.value, "remaining_gap": self.remaining_gap, "campaign_id": self.campaign_id, "plan": self.plan, "assessments": self.assessments, "notes": self.notes}

    @property
    def valid(self) -> bool:
        return self.digest == sha256_json(self._hash_payload())

    def to_dict(self) -> dict[str, Any]:
        data = dict(self._hash_payload())
        data.update({"source_ids": list(self.source_ids), "dataset_ids": list(self.dataset_ids), "engine_ids": list(self.engine_ids), "run_ids": list(self.run_ids), "evidence_before": list(self.evidence_before), "evidence_after": list(self.evidence_after), "notes": list(self.notes), "digest": self.digest, "valid": self.valid})
        return data
