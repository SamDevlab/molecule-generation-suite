from __future__ import annotations

from research_os.benchmark import ScientificDecisionBenchmark
from research_os.core.types import EvidenceLevel
from research_os.external_evidence import ExternalEvidenceIntegrator
from research_os.oracle.provider import CodexLiveProvider
from tools.benchmark.master_validation_v40 import (
    _fixed_specs,
    _materialize_case,
    _reproduction_matrix,
    _sealed_mutation_blocked,
    _security_audit,
    _stress_tests,
)


def test_v40_fixed_matrix_has_required_domain_distribution() -> None:
    evidence = ("EVD-V40-FIXTURE",)
    specs = _fixed_specs(evidence)
    assert len(specs) == 100
    assert {item.category: sum(spec.category == item.category for spec in specs) for item in specs} == {
        "deterministic_molecular": 15,
        "ml_ood_uncertainty": 15,
        "docking_pharma": 15,
        "cantera_physics": 15,
        "battery_materials": 10,
        "knowledge_source_evidence": 10,
        "cross_domain": 10,
        "adversarial_no_decision": 10,
    }


def test_v40_cases_have_zero_decision_audit_failures() -> None:
    known = set()
    cases = [_materialize_case(spec, known)[0] for spec in _fixed_specs(("EVD-V40-FIXTURE",))]
    benchmark = ScientificDecisionBenchmark.from_cases(cases, commit="test", environment_hash="test", started_at="test", completed_at="test")
    assert benchmark.total_cases == 100
    assert benchmark.invariant_failures == 0
    assert benchmark.false_supported_decisions == 0
    assert benchmark.false_no_decisions == 0


def test_v40_reproduction_stress_and_security_matrices_are_sealed_passes() -> None:
    reproduction = _reproduction_matrix()
    assert reproduction["status"] == "PASS"
    assert reproduction["counts"] == {"total": 20, "reproduced": 14, "reproduced_with_environment_change": 3, "diverged": 3, "first_divergence": 3}
    assert len(_stress_tests()) == 50
    assert all(item["status"] == "PASS" for item in _stress_tests())
    assert _security_audit()["status"] == "PASS"


def test_v40_sealed_runs_and_evidence_level_guard_fail_closed() -> None:
    assert _sealed_mutation_blocked()
    assert ExternalEvidenceIntegrator.level_guard("E2_COMPUTATIONAL", "E4_CURATED_EXPERIMENTAL")["promotion_allowed"] is False
    assert tuple(item.value for item in EvidenceLevel)[:6] == ("E0_HEURISTIC", "E1_ML", "E2_COMPUTATIONAL", "E3_PHYSICS", "E4_CURATED_EXPERIMENTAL", "E5_VALIDATED_EXPERIMENTAL")


class _FinalExamTransport:
    available = True
    last_runtime_model = "gpt-test"
    last_cli_version = "test"

    def __call__(self, operation, payload, context):
        if operation == "final_autonomous_exam":
            return {"answerable": {"question": "Can CCO be calculated?"}, "no_decision": {"question": "Should OOD be ranked?"}, "external_blocker": {"question": "Can missing evidence be invented?"}}
        if operation == "final_exam_followups":
            return {"answers": [{"index": 1, "answer": "registered answer", "grounded_record_ids": ["GAP-1"], "limitations": []}]}
        raise AssertionError(operation)


def test_v40_live_provider_exposes_exam_operations_without_scientific_authority() -> None:
    provider = CodexLiveProvider(transport=_FinalExamTransport())
    exam = provider.final_autonomous_exam({})
    assert set(exam) == {"answerable", "no_decision", "external_blocker"}
    followups = provider.final_exam_followups({})
    assert followups["answers"][0]["grounded_record_ids"] == ["GAP-1"]
