"""Immutable contracts for integrating versioned external evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
import uuid

from research_os.core.hashing import sha256_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tuple(values: Sequence[Any] | None) -> tuple[str, ...]:
    return tuple(str(item) for item in values or ())


@dataclass(frozen=True)
class ExternalEvidenceUpdate:
    update_id: str
    source_id: str
    source_version: str
    dataset_id_optional: str | None
    evidence_ids: tuple[str, ...]
    affected_claim_ids: tuple[str, ...]
    affected_gap_ids: tuple[str, ...]
    affected_decision_ids: tuple[str, ...]
    compatibility_assessment: str | Mapping[str, Any]
    conflicts: tuple[str, ...]
    resulting_revisions: tuple[str, ...]
    created_at: str = field(default_factory=_now)
    digest: str | None = None

    def __post_init__(self) -> None:
        for name in ("evidence_ids", "affected_claim_ids", "affected_gap_ids", "affected_decision_ids", "conflicts", "resulting_revisions"):
            object.__setattr__(self, name, _tuple(getattr(self, name)))
        if not self.update_id.strip() or not self.source_id.strip() or not self.source_version.strip():
            raise ValueError("ExternalEvidenceUpdate requires source identity and version")
        if self.digest is None:
            object.__setattr__(self, "digest", sha256_json(self._hash_payload()))

    def _hash_payload(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("digest", None)
        for name in ("evidence_ids", "affected_claim_ids", "affected_gap_ids", "affected_decision_ids", "conflicts", "resulting_revisions"):
            data[name] = list(getattr(self, name))
        return data

    @property
    def valid(self) -> bool:
        return self.digest == sha256_json(self._hash_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_payload(), "digest": self.digest}


@dataclass(frozen=True)
class EvidenceDependencyAssessment:
    assessment_id: str
    evidence_ids: tuple[str, ...]
    shared_sources: tuple[str, ...]
    shared_datasets: tuple[str, ...]
    shared_models: tuple[str, ...]
    shared_runs: tuple[str, ...]
    shared_publications: tuple[str, ...]
    independence_status: str
    notes: tuple[str, ...] = ()
    created_at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        for name in ("evidence_ids", "shared_sources", "shared_datasets", "shared_models", "shared_runs", "shared_publications", "notes"):
            object.__setattr__(self, name, _tuple(getattr(self, name)))
        if self.independence_status not in {"INDEPENDENT", "PARTIALLY_DEPENDENT", "DEPENDENT", "UNKNOWN"}:
            raise ValueError("unknown evidence independence status")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for name in ("evidence_ids", "shared_sources", "shared_datasets", "shared_models", "shared_runs", "shared_publications", "notes"):
            data[name] = list(getattr(self, name))
        return data


__all__ = ["EvidenceDependencyAssessment", "ExternalEvidenceUpdate"]
