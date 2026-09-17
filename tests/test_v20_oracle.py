import pytest

from research_os.core.types import EvidenceLevel
from research_os.oracle import (
    AutonomousResearchLoop,
    ClaimTarget,
    LoopLimits,
    OracleAnswerStatus,
    OraclePlanner,
    PlanStep,
    PlanValidator,
    ResearchPlan,
    ResearchQuestion,
    ResearchMemory,
    RuleBasedLLMProvider,
)


def test_unknown_lab_and_cycle_are_rejected():
    question = ResearchQuestion("x", "general", "x")
    plan = ResearchPlan(question.question_id, (PlanStep("a", "NoLab", "nothing", requires=("b",)), PlanStep("b", "NoLab", "nothing", requires=("a",))))
    result = PlanValidator().validate(plan)
    assert result.status == "FAIL"
    assert {issue.rule_id for issue in result.issues} >= {"ORACLE-LAB-001", "ORACLE-DEPENDENCY-002"}


def test_missing_required_engine_is_indeterminate():
    question = ResearchQuestion("compare fuels", "aerospace", "compare fuels")
    plan = ResearchPlan(question.question_id, (PlanStep("c", "CombustionLab", "adiabatic_equilibrium_hp", {"fuel": "A", "mechanism": "missing", "temperature": {"value": 300, "unit": "K"}, "pressure": {"value": 1, "unit": "atm"}}, minimum_evidence_level=EvidenceLevel.E3_PHYSICS),))
    result = PlanValidator().validate(plan)
    assert result.status == "INDETERMINATE"
    assert result.first_loss.rule_id == "ORACLE-ENGINE-001"


def test_docking_clinical_claim_is_rejected_and_reformulated():
    result = OraclePlanner(RuleBasedLLMProvider()).ask("Use docking to prove that X cures Alzheimer.")
    assert result.reformulated_from
    assert result.plan.claim_targets[0].required_evidence_level is EvidenceLevel.E2_COMPUTATIONAL
    assert OraclePlanner().answer_from_plan(result).status is OracleAnswerStatus.REJECTED


def test_memory_continuation_creates_new_plan_without_mutating_old():
    question = ResearchQuestion("q", "general", "objective")
    old = ResearchPlan(question.question_id, (PlanStep("m", "MoleculeLab", "deterministic_properties", {"smiles": "CCO"}),))
    new_question, new = ResearchMemory().continue_research(old)
    assert new.rerun_of == old.plan_id
    assert new.plan_id != old.plan_id
    assert old.rerun_of is None


def test_bounded_loop_stops_on_indeterminate():
    loop = AutonomousResearchLoop(LoopLimits(max_iterations=5))
    result = loop.run(lambda _: {"status": "INDETERMINATE", "runs": 1}, lambda _: ())
    assert result.status == "INDETERMINATE"
    assert result.stop_reason == "indeterminate"

