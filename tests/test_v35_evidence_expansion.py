from dataclasses import FrozenInstanceError

import pytest

from research_os.core.types import EvidenceLevel
from research_os.evidence import EvidenceAgreementAssessment, EvidenceAgreementStatus
from research_os.knowledge import ClaimRevision, ClaimStatus, ScientificClaim


def test_evidence_agreement_is_hashed_without_summing_levels():
    assessment = EvidenceAgreementAssessment(
        claim_target="murine COX-2 / 1PXX docking under the declared protocol",
        evidence_ids=("EVD-TARGET", "EVD-DOCK-1", "EVD-DOCK-2"),
        conditions={"species": "Mus musculus", "structure_id": "1PXX"},
        consistency=EvidenceAgreementStatus.PARTIALLY_CONSISTENT,
        conflicts=("HEM was excluded from the prepared PDBQT receptor.",),
        strongest_supported_level=EvidenceLevel.E2_COMPUTATIONAL,
        limitations=("Docking score is not measured affinity.",),
    )
    assert assessment.valid
    assert assessment.to_dict()["strongest_supported_level"] == "E2_COMPUTATIONAL"
    assert "sum" not in assessment.to_dict()
    with pytest.raises(FrozenInstanceError):
        assessment.consistency = "CONFLICTING"


def test_claim_revision_preserves_previous_state_and_is_append_only():
    claim = ScientificClaim(
        "The initial target identity record does not support a docking claim.",
        "RUN-TARGET",
        ("EVD-TARGET",),
        EvidenceLevel.E4_CURATED_EXPERIMENTAL,
        ClaimStatus.INSUFFICIENT_EVIDENCE,
    )
    revision = ClaimRevision(
        revision_id="REV-COX2-02",
        claim_id="CLM-COX2-1PXX-V2",
        version=2,
        statement="The declared murine 1PXX protocol produced reproducible E2 docking outputs.",
        previous_status=claim.status,
        current_status=ClaimStatus.SUPPORTED,
        previous_evidence_ids=claim.evidence_ids,
        evidence_ids=("EVD-TARGET", "EVD-DOCK-1", "EVD-DOCK-2"),
        reason="Open Babel and AutoDock Vina were configured and sealed bundles were indexed.",
        supersedes=claim.claim_id,
        derived_from=("RUN-DOCK-1", "RUN-DOCK-2"),
    )
    assert revision.valid
    assert revision.to_dict()["previous_evidence_ids"] == ["EVD-TARGET"]
    assert revision.to_dict()["current_status"] == "SUPPORTED"
    assert claim.status is ClaimStatus.INSUFFICIENT_EVIDENCE
    with pytest.raises(ValueError):
        ClaimRevision("REV-BAD", claim.claim_id, 1, "bad", claim.status, claim.status, (), (), "bad")
