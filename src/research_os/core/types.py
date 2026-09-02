from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import hashlib, json, uuid

from research_os.core.hashing import sha256_json
from research_os.core.provenance import ProvenanceRecord

class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

class EvidenceLevel(str, Enum):
    E0_HEURISTIC = "E0_HEURISTIC"
    E1_ML = "E1_ML"
    E2_COMPUTATIONAL = "E2_COMPUTATIONAL"
    E3_PHYSICS = "E3_PHYSICS"
    E4_CURATED_EXPERIMENTAL = "E4_CURATED_EXPERIMENTAL"
    E5_VALIDATED_EXPERIMENTAL = "E5_VALIDATED_EXPERIMENTAL"

@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    kind: str
    level: EvidenceLevel
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    provenance_ids: tuple[str, ...] = ()
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass(frozen=True)
class GateResult:
    gate_id: str
    rule_id: str
    status: GateStatus
    reason: str
    evidence_ids: tuple[str, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)

@dataclass
class RunManifest:
    lab: str
    experiment: str
    inputs: dict[str, Any]
    config: dict[str, Any] = field(default_factory=dict)
    run_id: str = field(default_factory=lambda: f"RUN-{uuid.uuid4().hex[:12].upper()}")
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence: list[Evidence] = field(default_factory=list)
    provenance: list[ProvenanceRecord] = field(default_factory=list)
    gates: list[GateResult] = field(default_factory=list)

    @property
    def input_hash(self) -> str:
        return sha256_json(self.inputs)

    @property
    def status(self) -> str:
        if not self.gates:
            return "NOT_EVALUATED"
        return "PASS" if self.first_loss is None else self.first_loss.status.value

    @property
    def first_loss(self) -> GateResult | None:
        for gate in self.gates:
            if gate.status != GateStatus.PASS:
                return gate
        return None

    @property
    def passed(self) -> bool:
        return bool(self.gates) and self.first_loss is None

    def digest(self) -> str:
        data = asdict(self)
        blob = json.dumps(data, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()
