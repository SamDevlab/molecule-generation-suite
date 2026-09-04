"""Safety boundary for computational docking claims."""

from __future__ import annotations

from research_os.core.types import EvidenceLevel, GateResult, GateStatus

FORBIDDEN_DOCKING_CLAIM_TERMS = ("clinical", "treats", "safe", "efficacy", "therapeutic", "measured affinity", "experimentally validated")


def docking_claim_gate(statement: str, *, evidence_level: EvidenceLevel | str = EvidenceLevel.E2_COMPUTATIONAL) -> GateResult:
    value = evidence_level.value if hasattr(evidence_level, "value") else str(evidence_level)
    lowered = str(statement).lower()
    forbidden = [term for term in FORBIDDEN_DOCKING_CLAIM_TERMS if term in lowered]
    if forbidden:
        return GateResult("GATE-DOCKING-CLAIM", "DOCK-CLAIM-001", GateStatus.FAIL, "docking evidence cannot support clinical, safety, efficacy or experimental affinity claims", diagnostics={"forbidden_terms": forbidden, "evidence_level": value})
    return GateResult("GATE-DOCKING-CLAIM", "DOCK-CLAIM-001", GateStatus.PASS, "claim is limited to computational docking evidence", diagnostics={"evidence_level": value})


def validate_docking_claim(statement: str, *, evidence_level: EvidenceLevel | str = EvidenceLevel.E2_COMPUTATIONAL) -> bool:
    return docking_claim_gate(statement, evidence_level=evidence_level).status == GateStatus.PASS
