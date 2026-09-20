from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from research_os.external_evidence import ExternalEvidenceIntegrator
from research_os.molecular_discovery.biolab_loop import (
    BiolabScientificState,
    apply_e4_feedback,
    default_moldisc018_state,
    evaluate_next_action,
)


def test_first_state_selects_experiment_and_stops_same_level_computation() -> None:
    snapshot = evaluate_next_action(default_moldisc018_state())
    decision = snapshot.decision
    assert decision.selected_action == "EXPERIMENT"
    assert decision.target_gap == "GAP-EXPERIMENTAL-SOLUBILITY"
    assert decision.required_evidence == "E4_CURATED_EXPERIMENTAL"
    assert decision.current_evidence == "E2_COMPUTATIONAL"
    assert decision.status == "STOPPED"
    assert decision.stop_reason == "EXPERIMENTAL_VALIDATION_REQUIRED"
    assert decision.computational_continuation_allowed is False
    assert decision.next_generation_allowed is False
    recommendations = {item["label"]: item["recommendation"] for item in decision.assessments}
    assert recommendations == {
        "repeat/expand docking": "LOW_INFORMATION_GAIN",
        "pose-basin / reranking analysis": "DEFER",
        "generate another molecular series": "BLOCKED",
        "prepare physical solubility experiment": "PRIORITIZE_NOW",
    }


def test_same_level_guard_does_not_block_a_new_external_computational_blocker() -> None:
    state = BiolabScientificState(
        current_program="MOLDISC-018",
        current_evidence_levels=("E2_COMPUTATIONAL",),
        open_gaps=({"gap_id": "GAP-EXPERIMENTAL-SOLUBILITY", "required_evidence": "E4_CURATED_EXPERIMENTAL", "status": "OPEN", "computational_blocker": True},),
        external_dependencies=({"new_external_information": True},),
    )
    decision = evaluate_next_action(state).decision
    assert decision.computational_continuation_allowed is True
    assert decision.selected_action == "EXPERIMENT"


def test_feedback_marks_the_old_gap_and_recomputes_without_forcing_generation() -> None:
    state = default_moldisc018_state()
    update = {
        "evidence_ids": ("E4-BIOEXP-001-A0B0",),
        "affected_claim_ids": ("CLAIM-BIOLAB-PHYSICAL-FEEDBACK",),
        "affected_gap_ids": ("GAP-EXPERIMENTAL-SOLUBILITY",),
    }
    updated = apply_e4_feedback(state, update)
    assert "E4_CURATED_EXPERIMENTAL" in updated.current_evidence_levels
    assert updated.new_experimental_evidence_ids == ("E4-BIOEXP-001-A0B0",)
    assert updated.open_gaps[0]["status"] == "EVIDENCE_RECEIVED"
    next_decision = evaluate_next_action(updated).decision
    assert next_decision.target_gap != "GAP-EXPERIMENTAL-SOLUBILITY"
    assert next_decision.selected_action in {"EXPERIMENT", "STOP"}
    assert next_decision.next_generation_allowed is False


def test_external_dependency_marks_repeated_same_report_as_dependent() -> None:
    integrator = ExternalEvidenceIntegrator()
    result = integrator.assess_dependency(
        ("E4-A", "E4-B"),
        {
            "E4-A": {"source_ids": ["LAB-1"], "report_ids": ["REPORT-1"], "run_ids": ["RUN-1"]},
            "E4-B": {"source_ids": ["LAB-1"], "report_ids": ["REPORT-1"], "run_ids": ["RUN-1"]},
        },
    )
    assert result.independence_status == "DEPENDENT"


ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "experimental_packages" / "biolab-physical-loop-0"


def _synthetic_result() -> dict[str, object]:
    return json.loads((PACKAGE / "external_result_example_TEST_SYNTHETIC.json").read_text(encoding="utf-8"))


def test_synthetic_fixture_is_not_e4() -> None:
    from research_os.molecular_discovery.moldisc019 import validate_result

    result = validate_result(_synthetic_result(), PACKAGE)
    assert result["eligible_for_e4"] is False
    assert any(item["code"] == "TEST_SYNTHETIC_NOT_SCIENTIFIC_EVIDENCE" for item in result["errors"])


def test_identity_mismatch_fails_closed() -> None:
    from research_os.molecular_discovery.moldisc019 import validate_result

    result = _synthetic_result()
    result["actual_experiment"] = True
    result["synthetic"] = False
    result["evidence_classification"] = "E4_CURATED_EXPERIMENTAL"
    result["reported_inchikey_if_available"] = "WRONG-INCHIKEY"
    validation = validate_result(result, PACKAGE)
    assert validation["eligible_for_e4"] is False
    assert any(item["code"] == "EXPERIMENT_IDENTITY_MISMATCH" for item in validation["errors"])
