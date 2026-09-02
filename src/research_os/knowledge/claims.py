from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import uuid

from research_os.core.types import EvidenceLevel, RunManifest


class ClaimStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REJECTED = "REJECTED"


_LEVEL_ORDER = {
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

    def to_dict(self):
        data = asdict(self)
        data["minimum_evidence_level"] = self.minimum_evidence_level.value
        data["status"] = self.status.value
        return data


def claim_from_run(run: RunManifest, statement: str, *, minimum_evidence_level: EvidenceLevel, evidence_ids: tuple[str, ...] | None = None, limitations: tuple[str, ...] = ()) -> ScientificClaim:
    selected = [e for e in run.evidence if evidence_ids is None or e.evidence_id in evidence_ids]
    required = _LEVEL_ORDER[minimum_evidence_level]
    qualifies = [e for e in selected if _LEVEL_ORDER[e.level] >= required]
    status = ClaimStatus.SUPPORTED if run.passed and qualifies else ClaimStatus.INSUFFICIENT_EVIDENCE
    return ScientificClaim(statement=statement, run_id=run.run_id, evidence_ids=tuple(e.evidence_id for e in qualifies), minimum_evidence_level=minimum_evidence_level, status=status, limitations=limitations)
