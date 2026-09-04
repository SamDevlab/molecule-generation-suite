from research_os.core.types import EvidenceLevel
from research_os.decision import (
    BatteryDatasetQualityAssessment,
    BatteryProtocolComparability,
    BatteryProtocolMatchStatus,
    DecisionCriterion,
    DecisionStatus,
    DecisionStore,
    DockingProtocolVariability,
    DockingSeparationStatus,
    PlanParsimonyAssessment,
    SimulationExperimentComparison,
    SimulationExperimentStatus,
    ScientificDecision,
    audit_decision,
    evaluate_docking_separation,
    resolve_decision,
)
from research_os.evidence import EvidenceAgreementAssessment, EvidenceAgreementStatus
from research_os.knowledge import ClaimRevision, ClaimStatus


def _criteria():
    return (
        DecisionCriterion("C-MOL", "molecular_structure", "pass", True, minimum_evidence_level=EvidenceLevel.E2_COMPUTATIONAL, OOD_policy="REJECT", conditions={"representation": "SMILES"}, comparison_protocol="RDKit deterministic properties"),
        DecisionCriterion("C-OOD", "solubility_ood", "pass", True, maximum_uncertainty_optional=1.0, OOD_policy="REJECT", conditions={"dataset": "AqSolDB-G"}, comparison_protocol="scaffold split; residual interval"),
    )


def test_decision_contract_has_no_universal_score_and_refuses_ood():
    decision = resolve_decision(
        decision_id="DECISION-REAL-03",
        campaign_id="CAMP-MOL-SOL-DOCK",
        question_id="Q-REAL-03",
        decision_question="Can either candidate be selected under all declared gates?",
        options=("diclofenac", "celecoxib"),
        criteria=_criteria(),
        required_evidence=("EVD-MOL-A", "EVD-ML-A"),
        evidence_available=("EVD-MOL-A", "EVD-ML-A"),
        evaluations=(),
        conditions={"protocol": "declared before candidate evaluation"},
        uncertainties=("model residual interval retained",),
        OOD_flags=("celecoxib: OUT_OF_DOMAIN",),
    )
    assert decision.decision_status == DecisionStatus.NO_DECISION_OUT_OF_DOMAIN.value
    assert decision.selected_option is None
    assert "total_score" not in decision.to_dict()


def test_docking_variability_and_guard_are_protocol_limited():
    left = DockingProtocolVariability.from_scores("VINA-1PXX-GRID-A-V127", ("A1", "A2", "A3"), (-8.1, -8.2, -8.15), decision_relevance="same receptor/grid/exhaustiveness")
    right = DockingProtocolVariability.from_scores("VINA-1PXX-GRID-A-V127", ("B1", "B2", "B3"), (-8.17, -8.13, -8.16), decision_relevance="same receptor/grid/exhaustiveness")
    assessment = evaluate_docking_separation(left, right, option_a="diclofenac", option_b="celecoxib")
    assert assessment.status == DockingSeparationStatus.WITHIN_PROTOCOL_VARIABILITY.value
    assert left.score_min == -8.2
    assert left.score_max == -8.1
    assert "significance inference" in left.interpretation


def test_heterogeneous_evidence_and_revision_aliases_are_backward_compatible():
    assessment = EvidenceAgreementAssessment("target", ("E1", "E2"), {"temperature": 300}, EvidenceAgreementStatus.INSUFFICIENT_EVIDENCE, evidence_types=("molecule", "docking"), comparability="PARTIAL")
    assert assessment.assessment_id == assessment.agreement_id
    assert assessment.to_dict()["evidence_types"] == ["molecule", "docking"]
    revision = ClaimRevision("REV-2", "CLM-1", 2, "updated", ClaimStatus.INSUFFICIENT_EVIDENCE, ClaimStatus.SUPPORTED, (), ("E2",), "new run", previous_revision_id="REV-1", conditions={"protocol": "fixed"})
    assert revision.to_dict()["new_status"] == "SUPPORTED"
    assert revision.to_dict()["new_evidence_ids"] == ["E2"]
    assert revision.timestamp == revision.created_at


def test_audit_plan_parsimony_battery_and_comparison():
    decision = ScientificDecision("D-AUDIT", "CAMP", "Q", "choose", ("A", "B"), _criteria(), ("E1",), ("E1",), (), (), {"temperature_k": 300}, ("interval",), (), None, ("A", "B"), DecisionStatus.NO_DECISION_INSUFFICIENT_EVIDENCE, "no candidate met all gates", ("no unique selection",))
    audit = audit_decision(decision, known_evidence_ids={"E1"})
    assert audit.no_hidden_scoring and audit.no_evidence_inflation
    plan = PlanParsimonyAssessment("P", ("molecule", "solubility", "docking"), ("knowledge",), (), ("unsupported_materials",), False)
    assert not plan.minimal_sufficient
    quality = BatteryDatasetQualityAssessment("BAT", ("time", "voltage", "current"), ("capacity", "uncertainty"), ("E-BAT",), "PARTIALLY_RESOLVED")
    assert quality.to_dict()["missing_fields"] == ["capacity", "uncertainty"]
    protocol = BatteryProtocolComparability("BAT-CMP", "SRC-A", "SRC-B", ("temperature",), ("cycle_definition",), BatteryProtocolMatchStatus.PARTIAL_MATCH)
    assert protocol.to_dict()["status"] == "PARTIAL_MATCH"
    comparison = SimulationExperimentComparison.from_values(metric="temperature_k", simulated_evidence_ids=("E3",), experimental_evidence_ids=("E4",), condition_match="UNKNOWN", simulation_value=None, experimental_value=None, uncertainty=None, tolerance_protocol="predeclared")
    assert comparison.status == SimulationExperimentStatus.INSUFFICIENT_METADATA.value


def test_decision_store_is_append_only():
    store = DecisionStore()
    decision = ScientificDecision("D-STORE", "CAMP", "Q", "question", ("A",), _criteria(), (), (), (), (), {"protocol": "fixed"}, ("uncertainty retained",), (), None, ("A",), DecisionStatus.NO_DECISION_INSUFFICIENT_EVIDENCE, "not enough evidence", ("gap",))
    store.save(decision)
    assert store.get("D-STORE").digest == decision.digest
    assert len(store.list()) == 1
    store.close()


def test_web_decision_view_exposes_matrix_and_timeline(tmp_path):
    from research_os.web import build_default_application

    app = build_default_application(tmp_path, oracle_mode="test")
    decision = ScientificDecision("D-WEB", "CAMP", "Q", "question", ("A",), _criteria(), (), (), (), (), {"protocol": "fixed"}, ("uncertainty retained",), (), None, ("A",), DecisionStatus.NO_DECISION_INSUFFICIENT_EVIDENCE, "not enough evidence", ("gap",))
    app.decisions.save(decision)
    code, payload = app.dispatch("GET", "/api/decisions")
    assert code == 200
    assert payload["decisions"][0]["decision_id"] == "D-WEB"
    assert payload["evidence_matrix"]
    assert payload["timeline"][0]["decision_id"] == "D-WEB"
    app.close()
