from __future__ import annotations

import pytest

from research_os.external_evidence import EvidenceDependencyAssessment, ExternalEvidenceIntegrator, ExternalEvidenceUpdate


def test_external_update_is_digest_valid_and_append_only() -> None:
    update = ExternalEvidenceUpdate("UP-1", "SRC-1", "v1", "DATA-1", ("EVD-1",), ("CLM-1",), ("GAP-1",), ("DEC-1",), "compatible", (), ("REV-1",))
    integrator = ExternalEvidenceIntegrator()
    assert integrator.add_update(update) is update
    with pytest.raises(ValueError, match="already registered"):
        integrator.add_update(update)


def test_shared_lineage_is_dependency_not_double_confirmation() -> None:
    integrator = ExternalEvidenceIntegrator()
    result = integrator.assess_dependency(
        ("E1", "E2"),
        {
            "E1": {"source_ids": ["SRC"], "dataset_ids": ["DATA"], "model_ids": ["MODEL"], "run_ids": ["RUN"], "publication_ids": ["PAPER"]},
            "E2": {"source_ids": ["SRC"], "dataset_ids": ["DATA"], "model_ids": ["MODEL"], "run_ids": ["RUN"], "publication_ids": ["PAPER"]},
        },
    )
    assert isinstance(result, EvidenceDependencyAssessment)
    assert result.independence_status == "DEPENDENT"


def test_evidence_level_promotion_requires_actual_experiment() -> None:
    guard = ExternalEvidenceIntegrator.level_guard("E3_PHYSICS", "E4_CURATED_EXPERIMENTAL", actual_experiment=False)
    assert guard["promotion_allowed"] is False
    assert ExternalEvidenceIntegrator.level_guard("E3_PHYSICS", "E4_CURATED_EXPERIMENTAL", actual_experiment=True)["promotion_allowed"] is True
