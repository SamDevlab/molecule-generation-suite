from research_os.degradation import DegradationLab
from research_os.core.types import EvidenceLevel, GateStatus


def test_exposure_without_observation_is_insufficient_not_predicted():
    run = DegradationLab().run({"material": "IN718", "environment": "hydrogen", "temperature_k": 300.0})
    assert not run.passed
    assert run.first_loss.status == GateStatus.INSUFFICIENT_EVIDENCE
    assert any(e.kind == "degradation_exposure_record" for e in run.evidence)
    assert not any(e.kind == "degradation_observation" for e in run.evidence)


def test_curated_observation_requires_traceable_provenance():
    run = DegradationLab().run({
        "material": "IN718", "environment": "hydrogen", "temperature_k": 300.0,
        "observation": {"metric": "crack_growth_rate", "value": 1.2, "unit": "mm/s", "evidence_level": "E4_CURATED_EXPERIMENTAL"},
    })
    assert not run.passed
    assert run.first_loss.rule_id == "DEG-EVIDENCE-002"


def test_curated_observation_with_publication_provenance_passes():
    run = DegradationLab().run({
        "material": "IN718", "environment": "hydrogen", "temperature_k": 300.0,
        "provenance": {"source_type": "PUBLICATION", "source_id": "doi:example", "doi": "10.example/test"},
        "observation": {"metric": "mass_loss", "value": 0.2, "unit": "mg/cm2", "evidence_level": "E4_CURATED_EXPERIMENTAL"},
    })
    assert run.passed
    ev = next(e for e in run.evidence if e.kind == "degradation_observation")
    assert ev.level == EvidenceLevel.E4_CURATED_EXPERIMENTAL
