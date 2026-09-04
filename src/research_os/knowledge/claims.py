from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid

from research_os.core.hashing import sha256_json
from research_os.core.types import EvidenceLevel, RunManifest


class ClaimStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REJECTED = "REJECTED"


_LEVEL_ORDER = {
    EvidenceLevel.TEST_SYNTHETIC: -1,
    EvidenceLevel.E0_HEURISTIC: 0,
    EvidenceLevel.E1_ML: 1,
    EvidenceLevel.E2_COMPUTATIONAL: 2,
    EvidenceLevel.E3_PHYSICS: 3,
    EvidenceLevel.E4_CURATED_EXPERIMENTAL: 4,
    EvidenceLevel.E5_VALIDATED_EXPERIMENTAL: 5,
}


@dataclass(frozen=True)
class ScientificClaim:
    statement: str
    run_id: str
    evidence_ids: tuple[str, ...]
    minimum_evidence_level: EvidenceLevel
    status: ClaimStatus
    claim_id: str = field(default_factory=lambda: f"CLM-{uuid.uuid4().hex[:12].upper()}")
    limitations: tuple[str, ...] = ()
    conditions: dict[str, object] = field(default_factory=dict)
    supersedes: str | None = None
    derived_from: tuple[str, ...] = ()

    def to_dict(self):
        data = asdict(self)
        data["minimum_evidence_level"] = self.minimum_evidence_level.value
        data["status"] = self.status.value
        data["limitations"] = list(self.limitations)
        data["evidence_ids"] = list(self.evidence_ids)
        data["derived_from"] = list(self.derived_from)
        return data


@dataclass(frozen=True)
class ClaimRevision:
    """Append-only claim history; a revision never overwrites its predecessor."""

    revision_id: str
    claim_id: str
    version: int
    statement: str
    previous_status: ClaimStatus | str
    current_status: ClaimStatus | str
    previous_evidence_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    reason: str
    limitations: tuple[str, ...] = ()
    supersedes: str | None = None
    derived_from: tuple[str, ...] = ()
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "previous_status", self.previous_status if isinstance(self.previous_status, ClaimStatus) else ClaimStatus(str(self.previous_status)))
        object.__setattr__(self, "current_status", self.current_status if isinstance(self.current_status, ClaimStatus) else ClaimStatus(str(self.current_status)))
        object.__setattr__(self, "previous_evidence_ids", tuple(str(item) for item in self.previous_evidence_ids))
        object.__setattr__(self, "evidence_ids", tuple(str(item) for item in self.evidence_ids))
        object.__setattr__(self, "limitations", tuple(str(item) for item in self.limitations))
        object.__setattr__(self, "derived_from", tuple(str(item) for item in self.derived_from))
        if self.version < 2:
            raise ValueError("claim revisions start at version 2")
        if self.digest is None:
            object.__setattr__(self, "digest", sha256_json(self._hash_payload()))

    def _hash_payload(self) -> dict[str, object]:
        return {"revision_id": self.revision_id, "claim_id": self.claim_id, "version": self.version, "statement": self.statement, "previous_status": self.previous_status.value, "current_status": self.current_status.value, "previous_evidence_ids": self.previous_evidence_ids, "evidence_ids": self.evidence_ids, "reason": self.reason, "limitations": self.limitations, "supersedes": self.supersedes, "derived_from": self.derived_from, "created_at": self.created_at}

    @property
    def valid(self) -> bool:
        return self.digest == sha256_json(self._hash_payload())

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data.update({"previous_status": self.previous_status.value, "current_status": self.current_status.value, "previous_evidence_ids": list(self.previous_evidence_ids), "evidence_ids": list(self.evidence_ids), "limitations": list(self.limitations), "derived_from": list(self.derived_from), "valid": self.valid})
        return data


def claim_from_run(run: RunManifest, statement: str, *, minimum_evidence_level: EvidenceLevel, evidence_ids: tuple[str, ...] | None = None, limitations: tuple[str, ...] = (), conditions: dict[str, object] | None = None) -> ScientificClaim:
    selected = [e for e in run.evidence if evidence_ids is None or e.evidence_id in evidence_ids]
    required = _LEVEL_ORDER[minimum_evidence_level]
    qualifies = [e for e in selected if _LEVEL_ORDER.get(e.level, -1) >= required]
    status = ClaimStatus.SUPPORTED if run.passed and qualifies else ClaimStatus.INSUFFICIENT_EVIDENCE
    return ScientificClaim(statement=statement, run_id=run.run_id, evidence_ids=tuple(e.evidence_id for e in qualifies), minimum_evidence_level=minimum_evidence_level, status=status, limitations=limitations, conditions=dict(conditions or {}))
