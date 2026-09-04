"""Immutable contracts for historical scientific memory."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
import json
import uuid

from research_os.core.hashing import sha256_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _values(values: Sequence[Any] | None) -> tuple[str, ...]:
    return tuple(str(value) for value in values or ())


@dataclass(frozen=True)
class MemoryVersion:
    """A versioned source, dataset, model or engine state."""

    entity_id: str
    version: str
    timestamp: str
    provenance: tuple[str, ...] = ()
    status: str = "CURRENT"
    current: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", _values(self.provenance))
        if not self.entity_id.strip() or not self.version.strip():
            raise ValueError("MemoryVersion requires entity_id and version")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["provenance"] = list(self.provenance)
        return data


@dataclass(frozen=True)
class ResearchMemorySnapshot:
    """Indexed historical view; the Ledger remains the source of truth."""

    snapshot_id: str
    timestamp: str
    commit: str
    ledger_head: str
    active_campaigns: tuple[str, ...] = ()
    active_programs: tuple[str, ...] = ()
    verified_source_ids: tuple[str, ...] = ()
    dataset_versions: tuple[MemoryVersion, ...] = ()
    model_versions: tuple[MemoryVersion, ...] = ()
    engine_states: tuple[MemoryVersion, ...] = ()
    active_claim_ids: tuple[str, ...] = ()
    rejected_claim_ids: tuple[str, ...] = ()
    unresolved_gap_ids: tuple[str, ...] = ()
    decision_ids: tuple[str, ...] = ()
    digest: str | None = None

    def __post_init__(self) -> None:
        for name in ("active_campaigns", "active_programs", "verified_source_ids", "active_claim_ids", "rejected_claim_ids", "unresolved_gap_ids", "decision_ids"):
            object.__setattr__(self, name, _values(getattr(self, name)))
        for name in ("dataset_versions", "model_versions", "engine_states"):
            object.__setattr__(self, name, tuple(getattr(self, name) or ()))
        if self.digest is None:
            object.__setattr__(self, "digest", sha256_json(self._hash_payload()))

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp,
            "commit": self.commit,
            "ledger_head": self.ledger_head,
            "active_campaigns": list(self.active_campaigns),
            "active_programs": list(self.active_programs),
            "verified_source_ids": list(self.verified_source_ids),
            "dataset_versions": [item.to_dict() for item in self.dataset_versions],
            "model_versions": [item.to_dict() for item in self.model_versions],
            "engine_states": [item.to_dict() for item in self.engine_states],
            "active_claim_ids": list(self.active_claim_ids),
            "rejected_claim_ids": list(self.rejected_claim_ids),
            "unresolved_gap_ids": list(self.unresolved_gap_ids),
            "decision_ids": list(self.decision_ids),
        }

    @property
    def valid(self) -> bool:
        return self.digest == sha256_json(self._hash_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_payload(), "digest": self.digest}


@dataclass(frozen=True)
class TemporalMemoryRecord:
    record_id: str
    record_type: str
    timestamp: str
    entity_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    provenance_ids: tuple[str, ...] = ()
    version: str | None = None
    status: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", dict(self.payload or {}))
        object.__setattr__(self, "provenance_ids", _values(self.provenance_ids))
        if not self.record_id.strip() or not self.record_type.strip() or not self.entity_id.strip():
            raise ValueError("TemporalMemoryRecord requires identity")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["provenance_ids"] = list(self.provenance_ids)
        return data


@dataclass(frozen=True)
class DecisionEvolution:
    """Append-only relationship between two preserved decision versions."""

    evolution_id: str
    previous_decision_id: str
    current_decision_id: str
    relation: str
    previous_status: str
    current_status: str
    new_evidence_ids: tuple[str, ...]
    rationale: str
    timestamp: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "new_evidence_ids", _values(self.new_evidence_ids))
        if self.relation not in {"supersedes", "derived_from", "invalidated_by", "re-evaluated_by"}:
            raise ValueError("unsupported decision lineage relation")
        if not self.rationale.strip():
            raise ValueError("decision evolution requires rationale")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["new_evidence_ids"] = list(self.new_evidence_ids)
        return data


@dataclass(frozen=True)
class TemporalQueryResult:
    query_id: str
    query: str
    answer: str
    grounded: bool
    source_of_truth: str
    record_ids: tuple[str, ...] = ()
    run_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    dataset_versions: tuple[str, ...] = ()
    model_versions: tuple[str, ...] = ()
    engine_states: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()
    decision_ids: tuple[str, ...] = ()
    gap_ids: tuple[str, ...] = ()
    stale_items: tuple[str, ...] = ()
    conversation_memory_ignored: bool = True
    as_of: str | None = None
    digest: str | None = None

    def __post_init__(self) -> None:
        for name in ("record_ids", "run_ids", "source_ids", "dataset_versions", "model_versions", "engine_states", "claim_ids", "decision_ids", "gap_ids", "stale_items"):
            object.__setattr__(self, name, _values(getattr(self, name)))
        if self.digest is None:
            object.__setattr__(self, "digest", sha256_json(self._hash_payload()))

    def _hash_payload(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("digest", None)
        for name in ("record_ids", "run_ids", "source_ids", "dataset_versions", "model_versions", "engine_states", "claim_ids", "decision_ids", "gap_ids", "stale_items"):
            data[name] = list(getattr(self, name))
        return data

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_payload(), "digest": self.digest}


__all__ = ["DecisionEvolution", "MemoryVersion", "ResearchMemorySnapshot", "TemporalMemoryRecord", "TemporalQueryResult"]
