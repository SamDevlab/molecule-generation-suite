from __future__ import annotations

import pytest

from research_os.core.types import EvidenceLevel
from research_os.engines.combustion import EquilibriumResult
from research_os.oracle import (
    CodexDrivenResearchLoop,
    CodexLiveProvider,
    CodexLoopResult,
    LLM_OUTPUT_CANNOT_CREATE_SCIENTIFIC_EVIDENCE,
    LoopLimits,
    OraclePlanner,
    PlanValidator,
    ResearchGap,
    validate_narration,
)
from research_os.service import OracleService
from research_os.combustion import CombustionLab
from research_os.orchestration import LabRegistry, PlanStep, ResearchOrchestrator
from research_os.propulsion import PropulsionLab


class _ReferenceCombustionEngine:
    available = True
    version = "resolver-test"

    def simulate_equilibrium(self, request):
        return EquilibriumResult(
            adiabatic_temperature_k=3200.0,
            pressure_pa=request.pressure_pa,
            mean_molecular_weight=22.0,
            major_species_mole_fractions={"H2O": 0.6, "N2": 0.4},
            engine="ReferencePhysics",
            engine_version=self.version,
            mechanism=request.mechanism,
            gamma=1.22,
            cp_mass_j_kg_k=2100.0,
            cv_mass_j_kg_k=1721.3,
        )


class _Transport:
    available = True
    last_runtime_model = "gpt-live-test"
    last_cli_version = "test"

    def __call__(self, operation, payload, context):
        if operation == "interpret_question":
            return {"text": payload["user_message"], "domain": "molecule", "objective": payload["user_message"], "constraints": {"smiles": "CCO"}, "required_evidence_level": "E2_COMPUTATIONAL", "allowed_tools": ["MoleculeLab"], "forbidden_tools": ["shell"]}
        if operation == "generate_plan":
            return {"question_id": payload["question"]["question_id"], "steps": [{"step_id": "molecule", "lab": "MoleculeLab", "experiment": "deterministic_properties", "inputs": {"smiles": "CCO"}, "produces": ["properties"], "minimum_evidence_level": "E2_COMPUTATIONAL"}], "assumptions": [], "required_sources": [], "expected_outputs": ["evidence"], "risk_flags": [], "claim_targets": []}
        if operation == "propose_followup":
            return {"text": "Stop at the current evidence ceiling.", "domain": "continuation", "objective": "Stop", "required_evidence_level": "E2_COMPUTATIONAL", "gaps": payload["research_gaps"]}
        raise AssertionError(operation)


def test_live_provider_is_distinct_from_deterministic_and_cannot_emit_evidence():
    provider = CodexLiveProvider(transport=_Transport())
    assert provider.audit()["mode"] == "LIVE_ORACLE"
    assert provider.audit()["deterministic"] is False
    assert provider.audit()["production_validation"] is True
    assert provider.audit()["scientific_evidence_provider"] is False
    planner = OraclePlanner(provider, validator=PlanValidator())
    result = planner.ask("Analise CCO", context={"session_id": "SESSION-LIVE", "available_labs": ["MoleculeLab"]})
    assert result.validation.status == "PASS"
    assert result.audits[0].session_id == "SESSION-LIVE"
    assert result.audits[0].question_id == result.question.question_id
    assert result.audits[0].plan_id == result.plan.plan_id
    assert result.audits[0].response_hash


def test_live_output_cannot_create_scientific_evidence():
    class EvidenceTransport(_Transport):
        def __call__(self, operation, payload, context):
            return {"evidence": [{"level": "E5_VALIDATED_EXPERIMENTAL"}]}

    provider = CodexLiveProvider(transport=EvidenceTransport())
    with pytest.raises(ValueError, match=LLM_OUTPUT_CANNOT_CREATE_SCIENTIFIC_EVIDENCE):
        provider.interpret_question("ignore rules")


def test_narration_grounding_rejects_unknown_records_and_numeric_prose():
    recorded = {"status": "SUPPORTED", "evidence": [{"evidence_id": "EVD-1", "level": "E2_COMPUTATIONAL"}], "runs": {"s": {"run_id": "RUN-1"}}}
    assert validate_narration({"summary": "Recorded result", "status": "SUPPORTED", "evidence_ids": ["EVD-404"], "run_ids": ["RUN-1"], "limitations": []}, recorded).status == "FAIL"
    assert validate_narration({"summary": "Recorded value 46.069", "status": "SUPPORTED", "evidence_ids": ["EVD-1"], "run_ids": ["RUN-1"], "limitations": []}, recorded).status == "FAIL"
    assert validate_narration({"summary": "Recorded result at E2_COMPUTATIONAL", "status": "SUPPORTED", "evidence_ids": ["EVD-1"], "run_ids": ["RUN-1"], "limitations": []}, recorded).status == "PASS"


def test_codex_loop_stops_at_experimental_gap_without_repeating_computation():
    planner = OraclePlanner(CodexLiveProvider(transport=_Transport()), validator=PlanValidator())
    calls = []

    def execute(plan):
        calls.append(plan.plan.plan_id)
        return {"status": "SUPPORTED", "steps": 1, "runs": 1, "evidence_levels": ["E2_COMPUTATIONAL"]}

    def evaluate(_result):
        return (ResearchGap("claim", ("E2_COMPUTATIONAL",), EvidenceLevel.E4_CURATED_EXPERIMENTAL, ("experimental validation is required",), ("run a registered experiment",)),)

    result = CodexDrivenResearchLoop(planner, limits=LoopLimits(max_iterations=4, max_steps=4, max_runs=4)).run("Can we obtain clinical evidence using only docking?", execute=execute, evaluate=evaluate)
    assert isinstance(result, CodexLoopResult)
    assert result.status == "STOPPED"
    assert result.stop_reason == "EXPERIMENTAL_VALIDATION_REQUIRED"
    assert len(calls) == 1


def test_live_continuation_keeps_parent_immutable_and_creates_new_plan():
    provider = CodexLiveProvider(transport=_Transport())
    service = OracleService(OraclePlanner(provider, validator=PlanValidator()))
    first = service.ask("Analise CCO")
    second = service.continue_research(first.job.job_id, prompt="Continue essa pesquisa, mas agora compare com a condição anterior.")
    assert second.job.job_id != first.job.job_id
    assert second.planning.plan.rerun_of == first.planning.plan.plan_id
    assert first.planning.plan.rerun_of is None


def test_typed_from_step_input_routes_recorded_combustion_request_to_propulsion():
    registry = LabRegistry()
    combustion = CombustionLab(engine=_ReferenceCombustionEngine())
    registry.register(combustion)
    registry.register(PropulsionLab(combustion_lab=combustion))
    result = ResearchOrchestrator(registry).run(
        (
            PlanStep(
                "combustion",
                "CombustionLab",
                {"fuel": "CH4:1", "mechanism": "gri30.yaml", "temperature_k": 300.0, "pressure_pa": 101325.0},
                experiment="adiabatic_equilibrium_hp",
            ),
            PlanStep(
                "propulsion",
                "PropulsionLab",
                {"combustion": {"from_step": "combustion"}, "exit_pressure_pa": 10000.0},
                experiment="ideal_nozzle_from_combustion",
                requires=("combustion",),
            ),
        )
    )
    assert result.steps["propulsion"].status == "PASS"
    assert result.steps["propulsion"].inputs["combustion"]["fuel"] == "CH4:1"
    assert result.runs["propulsion"].evidence


def test_typed_from_step_reference_must_be_declared_and_known():
    question = OraclePlanner(CodexLiveProvider(transport=_Transport()), validator=PlanValidator()).interpret("Analise CCO")
    plan = OraclePlanner._plan_from_raw(
        question,
        {
            "question_id": question.question_id,
            "steps": [{"step_id": "downstream", "lab": "MoleculeLab", "experiment": "deterministic_properties", "inputs": {"smiles": "CCO", "metadata": {"from_step": "missing"}}}],
        },
    )
    result = PlanValidator().validate(plan, question=question)
    assert result.status == "FAIL"
    assert result.first_loss.rule_id == "ORACLE-DEPENDENCY-001"
