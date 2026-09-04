from research_os.benchmark import (
    DecisionBenchmarkCase,
    ScientificDecisionBenchmark,
    SemanticDecisionConsistency,
    audit_false_no_decision,
    audit_false_supported_decision,
)
from research_os.core.types import EvidenceLevel
from research_os.decision import CriterionEvaluation, DecisionCriterion, DecisionStatus, resolve_decision


def _decision(status=DecisionStatus.SUPPORTED_DECISION, *, ood_flags=()):
    criteria = (
        DecisionCriterion(
            "C1", "declared_boundary", "pass", True,
            minimum_evidence_level=EvidenceLevel.E2_COMPUTATIONAL,
            maximum_uncertainty_optional=1.0,
            OOD_policy="RETAIN_AND_DO_NOT_RANK_OOD",
            conditions={"protocol": "fixed"},
            comparison_protocol="bounded",
        ),
    )
    evaluations = (
        CriterionEvaluation("A", "C1", status == DecisionStatus.SUPPORTED_DECISION, ("E1",), uncertainty=0.2),
        CriterionEvaluation("B", "C1", False, ("E1",), uncertainty=0.2),
    )
    return resolve_decision(
        decision_id="D-V37-TEST", campaign_id="CAMP", question_id="Q", decision_question="choose",
        options=("A", "B"), criteria=criteria, required_evidence=("E1",), evidence_available=("E1",),
        evaluations=evaluations, conditions={"protocol": "fixed"}, uncertainties=("interval retained",),
        OOD_flags=ood_flags,
    )


def _case(status: str, *, expected: str | None = None, passed: bool = True):
    return DecisionBenchmarkCase(
        "CASE", "FIXED", "molecular", "question", "pt-BR", ({"criterion_id": "C1", "metric": "boundary"},),
        ("SRC",), (), (), (), ("CRITERIA_DECLARED",), expected, status, ("E1",), False,
        ("uncertainty retained",), {"protocol": "fixed"}, "D-V37-TEST", {"passed": passed},
    )


def test_benchmark_object_counts_and_digest_round_trip():
    benchmark = ScientificDecisionBenchmark.from_cases(
        (_case(DecisionStatus.SUPPORTED_DECISION.value, expected=DecisionStatus.SUPPORTED_DECISION.value),
         _case(DecisionStatus.NO_DECISION_INSUFFICIENT_EVIDENCE.value, expected=DecisionStatus.NO_DECISION_INSUFFICIENT_EVIDENCE.value)),
        commit="abc", environment_hash="env", started_at="start", completed_at="end",
    )
    assert benchmark.total_cases == 2
    assert benchmark.supported_decisions == 1
    assert benchmark.no_decisions == 1
    assert ScientificDecisionBenchmark.from_dict(benchmark.to_dict()).digest == benchmark.digest


def test_false_supported_detector_flags_ood_bypass_but_allows_recorded_ood():
    bypass = audit_false_supported_decision(_decision(), case_ood=True, uncertainty_relevant=True)
    assert bypass.detected is True
    assert "OOD_IGNORED" in bypass.flags
    recorded = audit_false_supported_decision(_decision(ood_flags=("candidate: OUT_OF_DOMAIN",)), case_ood=True, uncertainty_relevant=True)
    assert recorded.detected is False


def test_false_no_decision_detector_only_flags_known_available_truth():
    decision = _decision()
    finding = audit_false_no_decision(decision, expected_status=DecisionStatus.SUPPORTED_DECISION.value, deterministic_available=True)
    assert finding.detected is False
    refused = _decision(DecisionStatus.NO_DECISION_INSUFFICIENT_EVIDENCE)
    finding = audit_false_no_decision(refused, expected_status=DecisionStatus.SUPPORTED_DECISION.value, deterministic_available=True)
    assert finding.detected is True
    assert "KNOWN_SUPPORTED_CASE_REFUSED" in finding.flags


def test_semantic_consistency_contract_is_machine_readable():
    record = SemanticDecisionConsistency("A", ("A-1", "A-2", "A-3"), ("SUPPORTED_DECISION",) * 4, (("E1",),) * 4, (("boundary",),) * 4, True)
    payload = record.to_dict()
    assert payload["consistent"] is True
    assert payload["evidence_sets"] == [["E1"]] * 4
