from __future__ import annotations

import pytest

from research_os.impact import (
    ConfidenceFailureCase,
    ConditionDependentDecision,
    ImpactStatus,
    ProtocolSensitivityAssessment,
    ResearchOutcomeImpact,
    ResearchOutcomeImpactStore,
)


def _impact(**changes):
    values = dict(
        impact_id="IMP-1", program_id="PROG-1", campaign_ids=("CAMP-1",),
        initial_question="What changed?", prior_state_summary="The prior state had one open gap.",
        prior_claim_ids=("CLM-OLD",), prior_decision_ids=(), prior_gap_ids=("GAP-1",),
        new_source_ids=("SRC-1",), new_dataset_ids=(), new_run_ids=("RUN-1",),
        new_evidence_ids=("EVD-1",), new_claim_ids=(), revised_claim_ids=("CLM-OLD",),
        new_decision_ids=(), revised_decision_ids=(), resolved_gap_ids=(),
        partially_resolved_gap_ids=("GAP-1",), new_gap_ids=("GAP-2",),
        uncertainty_changed=True, comparability_changed=True,
        actionable_next_step="Acquire an independent compatible source.", external_validation_required=True,
        impact_status=ImpactStatus.KNOWLEDGE_CHANGED, summary="The claim was limited and the gap was refined.",
    )
    values.update(changes)
    return ResearchOutcomeImpact(**values)


def test_impact_is_hashed_and_round_trips_without_a_magic_score():
    record = _impact()
    assert record.valid
    payload = record.to_dict()
    assert "impact_score" not in payload
    assert ResearchOutcomeImpact.from_dict(payload) == record


def test_impact_store_is_append_only():
    store = ResearchOutcomeImpactStore()
    store.append(_impact())
    with pytest.raises(ValueError, match="append-only"):
        store.append(_impact())


def test_protocol_sensitivity_requires_limits_and_preserves_variant_values():
    assessment = ProtocolSensitivityAssessment(
        "PSA-1", "CAMP-1", "temperature_k", 300.0, (310.0,), ("RUN-1", "RUN-2"),
        "adiabatic_temperature_k", {"range_k": 12.0}, False, True,
        "The trend is stable but the absolute output is protocol-sensitive.",
        ("gri30 is not universal experimental validation",),
    )
    assert assessment.to_dict()["alternate_values"] == [310.0]


def test_confidence_failure_recomputes_absolute_error():
    case = ConfidenceFailureCase("C1=CC=CC=C1", -1.0, -3.0, 2.0, 0.1, "IN_DOMAIN", "benzene", "AqSolDB", "low uncertainty did not prevent a large residual")
    assert case.to_dict()["absolute_error"] == 2.0
    with pytest.raises(ValueError):
        ConfidenceFailureCase("CCO", 0.0, 1.0, 0.2, 0.1, "OOD", "ethanol", "AqSolDB", "bad error")


def test_condition_dependent_decision_keeps_both_protocols():
    decision = ConditionDependentDecision("DEC-1", "P-A", "H2 wins", "P-B", "CH4 wins", True, "the ranking reverses", {"temperature_k": [300, 500]})
    assert decision.to_dict()["changed"] is True
    assert decision.to_dict()["protocol_a"] == "P-A"
