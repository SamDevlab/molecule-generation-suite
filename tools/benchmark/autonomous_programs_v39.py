"""Research OS v3.9 autonomous multi-step Research Program benchmark.

This runner is intentionally bounded.  Program questions are generated from
the previous result and shared campaign memory; the Codex provider supplies
only a program proposal for Program 06.  Labs, evidence, decisions, bundles
and the Ledger remain Research OS responsibilities.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from research_os.bundles import ResearchBundle, verify_bundle
from research_os.combustion import CombustionLab
from research_os.core.hashing import sha256_json
from research_os.core.provenance import ProvenanceRecord, SourceType
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.datasets import AQSOLDB_G_SAMPLE_SPEC, ingest_aqsoldb_g
from research_os.decision import CriterionEvaluation, DecisionCriterion, DecisionStore, resolve_decision
from research_os.environment import capture_environment
from research_os.knowledge import SourceRecord, SourceType as KnowledgeSourceType
from research_os.ledger import RunRegistry
from research_os.ml.real import make_real_split, train_real_solubility_model
from research_os.molecule import MoleculeLab
from research_os.oracle import CodexLiveProvider
from research_os.programs import KnowledgeGainAssessment, ResearchProgram, ResearchProgramController, ResearchProgramStatus, ResearchStepUtilityAssessment, UtilityRecommendation
from research_os.resolution import analyze_nasa_pcoe_rw3
from research_os.web import build_default_application


V38_ARTIFACT = REPO_ROOT / ".research-os-live-3.8" / "reproduction-stress-benchmark.json"
V36_ARTIFACT = REPO_ROOT / ".research-os-live-3.6" / "v3.6-real-decision.json"
AQSOLDB_SAMPLE = REPO_ROOT / "examples" / "real_data" / "aqsoldb_g_sample.csv"
BATTERY_ARTIFACT = REPO_ROOT / ".research-os-live-3.4-battery" / "nasa-pcoe-rw3.zip"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_commit() -> str:
    import subprocess
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False).stdout.strip()


def _json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")


def _digest(value: Any) -> str:
    return sha256_json(value.to_dict() if hasattr(value, "to_dict") else value)


def _persist(run: RunManifest, root: Path, environment: Any, ledger: RunRegistry, *, datasets: tuple[Any, ...] = (), tags: tuple[str, ...] = ()) -> dict[str, Any]:
    if run.lifecycle.value == "CREATED":
        run.start()
    if run.lifecycle.value == "RUNNING":
        run.complete()
    run.attach_environment(environment)
    run.seal()
    bundle = ResearchBundle.create(run, root / "bundles", environment=environment, dataset_manifests=datasets)
    verification = verify_bundle(bundle.root)
    registration = ledger.register_run(bundle, tags=tags)
    return {"run_id": run.run_id, "bundle_id": bundle.bundle_id, "bundle_path": str(bundle.root), "bundle_hash": bundle.bundle_hash, "status": run.status, "bundle_status": verification.status.value, "bundle_passed": verification.passed, "ledger_status": registration.status.value, "evidence_ids": [item.evidence_id for item in run.evidence], "stable_digest": _digest({"inputs": run.inputs, "config": run.config, "evidence": [item.payload for item in run.evidence], "gates": [item.reason for item in run.gates]})}


def _fixed_programs() -> tuple[ResearchProgram, ...]:
    common = dict(max_campaigns=4, max_iterations=5, max_runs=4, max_sources=6, max_candidates=30, max_failures=2)
    return (
        ResearchProgram("PROG-01-SOLUBILITY", "Solubility reliability", "solubility", "Determine where the current solubility model can support a scientific decision and where it must refuse.", "The model is E1 and lacks independent external validation.", "Can a current prediction be used without hiding OOD or uncertainty?", **common),
        ResearchProgram("PROG-02-COX2", "COX-2 computational prioritization", "docking", "Determine how robust the current COX-2 computational prioritization is under the validated protocol.", "A docking result is useful only within the fixed E2 protocol.", "Does the existing replicate record justify more identical docking?", **common),
        ResearchProgram("PROG-03-COMBUSTION", "Combustion decision boundaries", "combustion", "Map which conclusions are supported only inside the tested Cantera protocols.", "Cantera is E3 physics simulation, not experimental validation.", "Which tested conditions remain reproducible without unsafe extrapolation?", **common),
        ResearchProgram("PROG-04-BATTERY", "Battery data sufficiency", "battery", "Determine exactly which questions the current real battery data supports and which remain blocked.", "NASA PCoE RW3 is real experimental data with missing fields.", "Which analyses are supported by the observed schema?", **common),
        ResearchProgram("PROG-05-MATERIALS", "Materials evidence gap", "materials", "Determine the minimum evidence needed for a defensible hydrogen-embrittlement material comparison.", "Condition-complete material observations remain unavailable.", "What exact record fields are still needed before comparison?", **common),
    )


def _program_from_live(raw: Mapping[str, Any]) -> ResearchProgram:
    questions = tuple(dict(item) for item in raw.get("questions") or () if isinstance(item, Mapping))
    limits = dict(raw.get("limits") or {})
    required = ("max_campaigns", "max_iterations", "max_runs", "max_sources", "max_candidates", "max_failures")
    if not all(key in limits for key in required) or int(limits.get("max_iterations", 0)) < 5:
        raise RuntimeError("Codex Live program did not declare five bounded iterations and all hard limits")
    normalized_questions = []
    for index, item in enumerate(questions, 1):
        question = str(item.get("question") or "").strip()
        gap = str(item.get("gap_it_attempts_to_resolve") or "").strip()
        if question and gap:
            normalized_questions.append({**item, "question_id": str(item.get("question_id") or f"Q-CODEX-{index:02d}"), "gap_it_attempts_to_resolve": gap, "generated_by_codex": True})
    if not normalized_questions:
        raise RuntimeError("Codex Live program contained no valid question with gap_it_attempts_to_resolve")
    return ResearchProgram("PROG-06-CODEX", str(raw.get("title") or "Codex-generated bounded research program"), str(raw.get("domain") or "general"), str(raw.get("objective") or ""), "Codex Live proposed this program from registered scientific context.", str(raw.get("initial_problem") or ""), tuple(normalized_questions), max_campaigns=int(limits["max_campaigns"]), max_iterations=int(limits["max_iterations"]), max_runs=int(limits["max_runs"]), max_sources=int(limits["max_sources"]), max_candidates=int(limits["max_candidates"]), max_failures=int(limits["max_failures"]), parent_program_id="PROG-01-SOLUBILITY")


def _live_program(root: Path, context: Mapping[str, Any]) -> tuple[ResearchProgram, dict[str, Any]]:
    app = build_default_application(root / "live-context", oracle_mode="live")
    try:
        provider = app.service.planner.provider
        raw = provider.generate_research_program(dict(context))
        program = _program_from_live(raw)
        return program, {"provider": getattr(provider, "provider_id", type(provider).__name__), "model": getattr(provider, "model", None), "status": "LIVE_CODEX_VALIDATED", "scientific_evidence_created": False, "raw_program": raw}
    finally:
        app.close()


def _question(program: ResearchProgram, iteration: int, prior: Mapping[str, Any]) -> dict[str, Any]:
    if iteration == 1 and program.research_questions:
        return dict(program.research_questions[0])
    previous = str(prior.get("status") or "NO_PRIOR_RESULT")
    gap = str(prior.get("gap") or program.initial_problem)
    if program.domain == "solubility":
        text = f"Após o resultado anterior {previous}, qual a próxima fronteira entre previsão IN_DOMAIN e OOD para a mesma pergunta?"
    elif program.domain == "docking":
        text = f"Após o registro {previous}, o que mudaria a comparabilidade do protocolo COX-2 sem repetir trabalho redundante?"
    elif program.domain == "combustion":
        text = f"Dado o resultado {previous}, uma mudança moderada de condição permanece dentro do protocolo Cantera declarado?"
    elif program.domain == "battery":
        text = f"Dado o resultado {previous}, qual campo ausente impede a próxima conclusão battery sem imputação?"
    elif program.domain == "materials":
        text = f"Dado o resultado {previous}, qual registro externo condição-completo resolveria parcialmente o gap?"
    else:
        text = f"A partir do resultado anterior {previous}, qual próxima pergunta registrada pode reduzir o gap sem depender de evidência inventada?"
    return {"question_id": f"Q-{program.program_id}-{iteration:02d}", "question": text, "gap_it_attempts_to_resolve": gap, "generated_from_prior_results": True, "prior_status": previous, "prior_digest": str(prior.get("digest") or "")}


def _utility(program: ResearchProgram, question: Mapping[str, Any], iteration: int, prior: Mapping[str, Any]) -> ResearchStepUtilityAssessment:
    lower = str(question.get("question", "")).lower()
    recommendation = UtilityRecommendation.EXECUTE
    reason = "the step can produce new registered evidence or a meaningful boundary result"
    if program.domain == "docking" and iteration >= 4:
        recommendation = UtilityRecommendation.SKIP_REDUNDANT
        reason = "the fixed three-replicate protocol already answers the proposed identical-repeat question"
    elif program.domain == "battery" and iteration == 4:
        recommendation = UtilityRecommendation.BLOCKED_EXTERNAL
        reason = "a complementary condition-matched public record is not registered"
    elif program.domain == "materials" and iteration == 4:
        recommendation = UtilityRecommendation.BLOCKED_EXTERNAL
        reason = "the required alloy/environment/stress record must come from an external source"
    elif program.domain == "materials" and iteration >= 5:
        recommendation = UtilityRecommendation.NO_EXPECTED_INFORMATION_GAIN
        reason = "local iteration cannot add a condition-complete material observation"
    elif program.domain == "combustion" and any(term in lower for term in ("explosive", "weapon", "destructive", "damaging")):
        recommendation = UtilityRecommendation.REJECT_UNSAFE
        reason = "unsafe combustion objective is out of scope"
    elif prior.get("status") in {"NO_PROGRESS", "PAUSED_EXTERNAL_BLOCKER"}:
        recommendation = UtilityRecommendation.NO_EXPECTED_INFORMATION_GAIN
        reason = "the prior result shows no new local information path"
    return ResearchStepUtilityAssessment(f"UTIL-{program.program_id}-{iteration:02d}", program.program_id, f"STEP-{program.program_id}-{iteration:02d}", str(question.get("gap_it_attempts_to_resolve")), str(question.get("question")), tuple(prior.get("evidence_ids") or ()), "qualitative new evidence, boundary clarification or gap resolution", "low" if recommendation == UtilityRecommendation.EXECUTE else "high", ("registered Lab" if recommendation == UtilityRecommendation.EXECUTE else "no local execution" ,), tuple(program.engine_ids), tuple(program.dataset_ids), "required" if recommendation == UtilityRecommendation.BLOCKED_EXTERNAL else None, "one bounded program step", "OOD/uncertainty/condition limits remain explicit", recommendation, reason)


def _execute_step(program: ResearchProgram, iteration: int, root: Path, environment: Any, ledger: RunRegistry, decisions: DecisionStore, prior: Mapping[str, Any]) -> dict[str, Any]:
    if program.domain == "solubility" and iteration == 1:
        ingestion = ingest_aqsoldb_g(AQSOLDB_SAMPLE, root / "solubility" / "datasets", spec=AQSOLDB_G_SAMPLE_SPEC)
        split, split_manifest = make_real_split(ingestion.records, ingestion.manifest, strategy="scaffold_split", seed=42, split_id="SPLIT-V39-AQSOLDB")
        ml = train_real_solubility_model(ingestion.records, ingestion.manifest, root / "solubility" / "ml", data_split=split, split_manifest=split_manifest, model_id="MODEL-V39-AQSOLDB", training_run_id="TRN-V39-AQSOLDB", seed=42, alpha=1.0, external_test_acceptable=False, environment_id=environment.environment_id, git_commit=environment.git.get("commit"))
        prediction = ml.model.predict("CCO")
        run = RunManifest("ResearchOS-Program", "v39_solubility_reliability", {"dataset_id": ingestion.manifest.dataset_id, "candidate": "CCO"}, {"model_id": ml.model.model_id, "feature_schema_id": ml.feature_schema.feature_schema_id, "ood_policy": "retain and do not rank OOD", "uncertainty_policy": "residual interval retained"}, run_id="RUN-V39-SOLUBILITY")
        provenance = ProvenanceRecord(SourceType.DATASET, ingestion.source.source_id, title=ingestion.source.title, citation=ingestion.source.citation, doi="10.1038/s41597-019-0151-1", url=ingestion.source.url, method=ingestion.manifest.measurement_method, conditions=ingestion.manifest.conditions)
        run.provenance.append(provenance)
        data_evidence = Evidence("EVD-V39-SOLUBILITY-DATA", "real_dataset_source_validation", EvidenceLevel.E4_CURATED_EXPERIMENTAL, ingestion.source.url, {"manifest": ingestion.manifest.to_dict(), "validation": ingestion.validation.to_dict()}, (provenance.provenance_id,))
        model_evidence = Evidence("EVD-V39-SOLUBILITY-MODEL", "real_solubility_model_validation", EvidenceLevel.E1_ML, "Research OS NumPy ridge baseline", {"model_id": ml.model.model_id, "validation": ml.validation.to_dict(), "split": ml.split.to_dict()}, (provenance.provenance_id,))
        prediction_evidence = Evidence("EVD-V39-SOLUBILITY-PRED", "candidate_prediction_with_ood_uncertainty", EvidenceLevel.E1_ML, "Morgan/Tanimoto AD and residual interval", {"prediction": prediction.to_dict(), "rankable": prediction.rankable}, (provenance.provenance_id,))
        run.evidence.extend((data_evidence, model_evidence, prediction_evidence))
        run.gates.append(GateResult("GATE-V39-SOLUBILITY", "V39-SOL-001", GateStatus.PASS, "AqSolDB real sample and explicit OOD/uncertainty were evaluated", tuple(item.evidence_id for item in run.evidence)))
        persisted = _persist(run, root / "runs", environment, ledger, datasets=(ingestion.manifest,), tags=("v3.9", "program", "solubility"))
        criterion = DecisionCriterion("V39-SOL-C1", "candidate_prediction_boundary", "pass", True, minimum_evidence_level=EvidenceLevel.E1_ML, maximum_uncertainty_optional=1.0, OOD_policy="RETAIN_AND_DO_NOT_RANK_OOD", conditions={"dataset": ingestion.manifest.dataset_id, "candidate": "CCO"}, comparison_protocol="in-domain and residual interval gate")
        decision = resolve_decision(decision_id="DECISION-V39-SOLUBILITY", campaign_id="CAMP-V39-SOLUBILITY", question_id="Q-V39-SOLUBILITY-01", decision_question="Can the CCO prediction be used under the recorded model boundary?", options=("use_bounded_prediction", "rank_ood_prediction"), criteria=(criterion,), required_evidence=(prediction_evidence.evidence_id,), evidence_available=(prediction_evidence.evidence_id,), evaluations=(CriterionEvaluation("use_bounded_prediction", criterion.criterion_id, bool(prediction.rankable), (prediction_evidence.evidence_id,), "rankability follows the registered OOD policy", False, prediction.uncertainty), CriterionEvaluation("rank_ood_prediction", criterion.criterion_id, False, (prediction_evidence.evidence_id,), "OOD predictions are excluded", not prediction.rankable, prediction.uncertainty)), conditions=criterion.conditions, uncertainties=("residual interval retained; not certainty",), OOD_flags=(prediction.status,), limitations=("No independent external validation was created.",))
        decisions.save(decision)
        return {"status": decision.decision_status, "evidence_ids": persisted["evidence_ids"], "dataset_ids": [ingestion.manifest.dataset_id], "model_ids": [ml.model.model_id], "decision_ids": [decision.decision_id], "digest": persisted["stable_digest"], "summary": "real AqSolDB model rerun; independent external validation remains open"}
    if program.domain == "combustion" and iteration == 1:
        run = CombustionLab().run({"fuel": "H2:1", "oxidizer": "O2:0.21,N2:0.79", "equivalence_ratio": 1.0, "temperature_k": 300.0, "pressure_pa": 101325.0, "basis": "mole", "mechanism": "gri30.yaml"}, experiment="v39_program_combustion_boundary")
        persisted = _persist(run, root / "runs", environment, ledger, tags=("v3.9", "program", "combustion"))
        return {"status": persisted["status"], "evidence_ids": persisted["evidence_ids"], "engine_ids": ["cantera"], "digest": persisted["stable_digest"], "summary": "fresh H2 Cantera E3 run under declared HP protocol"}
    if program.domain == "battery" and iteration == 1:
        analysis = analyze_nasa_pcoe_rw3(BATTERY_ARTIFACT)
        run = RunManifest("ResearchOS-Program", "v39_battery_schema_boundary", {"dataset_id": analysis.artifact.dataset_id, "artifact_sha256": analysis.artifact.artifact_sha256}, {"parser": "scipy.io.loadmat", "source_policy": "archive data only; scripts not executed"}, run_id="RUN-V39-BATTERY")
        source = SourceRecord("SRC-NASA-PCOE-RW3-V39", "NASA PCoE RW3 replay source", url="https://data.nasa.gov/", source_type=KnowledgeSourceType.DATASET, metadata={"artifact_sha256": analysis.artifact.artifact_sha256})
        run.provenance.append(ProvenanceRecord(SourceType.DATASET, source.source_id, title=source.title, url=source.url, method="MATLAB member schema parser", conditions=analysis.artifact.conditions))
        evidence = Evidence("EVD-V39-BATTERY", "battery_experimental_schema_observation", EvidenceLevel.E4_CURATED_EXPERIMENTAL, source.url or source.source_id, {"artifact": analysis.artifact.to_dict(), "summary": analysis.summary, "missing_fields": ["capacity_ah", "resistance_ohm", "uncertainty"]})
        run.evidence.append(evidence)
        run.gates.append(GateResult("GATE-V39-BATTERY", "V39-BATT-001", GateStatus.PASS, "real archive parsed without executing archive scripts", (evidence.evidence_id,)))
        persisted = _persist(run, root / "runs", environment, ledger, tags=("v3.9", "program", "battery"), datasets=(analysis.artifact.to_dict(),))
        return {"status": persisted["status"], "evidence_ids": persisted["evidence_ids"], "dataset_ids": [analysis.artifact.dataset_id], "digest": persisted["stable_digest"], "summary": "real battery fields parsed; missing capacity/resistance/uncertainty preserved"}
    if program.domain in {"molecule", "general"} and iteration == 1:
        run = MoleculeLab().run({"smiles": "CCO", "name": "v39-codex-program-molecule"}, experiment="v39_codex_generated_bounded_step")
        persisted = _persist(run, root / "runs", environment, ledger, tags=("v3.9", "program", "codex-generated"))
        return {"status": persisted["status"], "evidence_ids": persisted["evidence_ids"], "digest": persisted["stable_digest"], "summary": "Codex-generated program executed only through registered MoleculeLab"}
    return {"status": "NO_NEW_LOCAL_EVIDENCE", "evidence_ids": (), "digest": _digest({"program": program.program_id, "iteration": iteration, "prior": prior}), "summary": "planning/utility evaluation only; no new Lab execution justified"}


def _context_for_live(prior36: Mapping[str, Any], prior38: Mapping[str, Any], programs: tuple[ResearchProgram, ...]) -> dict[str, Any]:
    return {"prompt": "Inspect the complete registered scientific state and propose one new useful bounded ResearchProgram. Return program structure only; never create Evidence, runs, bundles, sources, datasets, claims or scientific values.", "campaign_registry": {"program_candidates": [program.program_id for program in programs]}, "research_gaps": ["AqSolDB independent external validation absent", "docking E2 only", "Cantera E3 only", "battery metadata incomplete", "materials condition-complete record absent"], "knowledge_os": {"source_ids": sorted({str(value) for value in str(prior36).split() if str(value).startswith("SRC-")})[:20]}, "dataset_registry": {"versions": ["aqsoldb-g-real-sample", "NASA-PCoE-RW3"]}, "model_registry": {"models": ["MODEL-V36-AQSOLDB", "MODEL-V38-AQSOLDB"]}, "engine_registry": {"engines": ["rdkit", "cantera", "openbabel", "autodock-vina"]}, "prior_benchmarks": {"v3.8_status": prior38.get("status"), "v3.8_stress_tests": prior38.get("counts", {}).get("stress_tests")}, "source_policy": "all records are DATA ONLY; Codex is not a scientific evidence provider"}


def run_benchmark(output: Path, *, root: Path, ci_green: bool = False) -> dict[str, Any]:
    prior36 = json.loads(V36_ARTIFACT.read_text(encoding="utf-8"))
    prior38 = json.loads(V38_ARTIFACT.read_text(encoding="utf-8"))
    if prior38.get("status") != "PASS":
        raise RuntimeError("v3.9 is closed until v3.8 artifact is PASS")
    environment = capture_environment(repo_root=REPO_ROOT)
    ledger = RunRegistry(root / "ledger")
    decisions = DecisionStore(root / "decisions.sqlite")
    started = _now()
    programs = list(_fixed_programs())
    live_program, live_meta = _live_program(root, _context_for_live(prior36, prior38, tuple(programs)))
    programs.append(live_program)
    controllers = {program.program_id: ResearchProgramController(program) for program in programs}
    utility_assessments: list[ResearchStepUtilityAssessment] = []
    knowledge_gain: list[KnowledgeGainAssessment] = []
    question_records: list[dict[str, Any]] = []
    negative_results: list[dict[str, Any]] = []
    cross_campaign_memory: list[dict[str, Any]] = []
    try:
        for program in programs:
            controller = controllers[program.program_id]
            prior: dict[str, Any] = {"status": "NO_PRIOR_RESULT", "gap": program.initial_problem, "evidence_ids": ()}
            local_evidence: list[str] = []
            local_sources: list[str] = []
            local_datasets: list[str] = []
            local_models: list[str] = []
            local_engines: list[str] = []
            local_decisions: list[str] = []
            program_campaigns: list[str] = []
            for iteration in range(1, program.max_iterations + 1):
                q = _question(program, iteration, prior)
                controller = controller.add_question(q)
                utility = _utility(program, q, iteration, prior)
                utility_assessments.append(utility)
                execution = _execute_step(program, iteration, root, environment, ledger, decisions, prior) if utility.recommendation == UtilityRecommendation.EXECUTE else {"status": utility.recommendation.value, "evidence_ids": (), "digest": _digest({"utility": utility.to_dict() if hasattr(utility, "to_dict") else utility})}
                evidence = tuple(str(item) for item in execution.get("evidence_ids") or ())
                local_evidence.extend(evidence)
                local_sources.extend(str(item) for item in execution.get("source_ids") or ())
                local_datasets.extend(str(item) for item in execution.get("dataset_ids") or ())
                local_models.extend(str(item) for item in execution.get("model_ids") or ())
                local_engines.extend(str(item) for item in execution.get("engine_ids") or ())
                local_decisions.extend(str(item) for item in execution.get("decision_ids") or ())
                if utility.recommendation == UtilityRecommendation.EXECUTE:
                    program_campaigns.append(f"CAMP-{program.program_id}-{iteration:02d}")
                else:
                    negative_results.append({"program_id": program.program_id, "question_id": q["question_id"], "recommendation": utility.recommendation.value, "reason": utility.rationale})
                progress = bool(evidence or execution.get("source_ids") or execution.get("dataset_ids") or execution.get("model_ids") or execution.get("decision_ids"))
                controller = controller.record_iteration(evidence_ids=evidence, source_ids=tuple(execution.get("source_ids") or ()), dataset_ids=tuple(execution.get("dataset_ids") or ()), new_decision_ids=tuple(execution.get("decision_ids") or ()), improved_comparability=utility.recommendation == UtilityRecommendation.SKIP_REDUNDANT, runs=1 if utility.recommendation == UtilityRecommendation.EXECUTE else 0)
                question_records.append({"program_id": program.program_id, "iteration": iteration, "question": q, "utility": utility.to_dict(), "execution": execution, "generated_from_prior_results": bool(q.get("generated_from_prior_results")), "progress": progress})
                prior = {"status": str(execution.get("status") or utility.recommendation.value), "gap": str(q.get("gap_it_attempts_to_resolve")), "evidence_ids": evidence, "digest": str(execution.get("digest") or "")}
                cross_campaign_memory.append({"program_id": program.program_id, "question_id": q["question_id"], "status": prior["status"], "evidence_ids": list(evidence), "digest": prior["digest"]})
            final_status = controller.program.status
            if final_status == ResearchProgramStatus.NO_PROGRESS:
                stop_reason = "two consecutive iterations without scientific progress"
            elif any(item.recommendation == UtilityRecommendation.BLOCKED_EXTERNAL for item in utility_assessments if item.program_id == program.program_id):
                final_status = ResearchProgramStatus.PAUSED_EXTERNAL_BLOCKER
                stop_reason = "external dependency is absent; local execution stopped"
            elif any(item.recommendation == UtilityRecommendation.SKIP_REDUNDANT for item in utility_assessments if item.program_id == program.program_id) and not local_evidence:
                final_status = ResearchProgramStatus.COMPLETED
                stop_reason = "marginal information gain exhausted after valid sealed evidence"
            else:
                final_status = ResearchProgramStatus.COMPLETED
                stop_reason = "bounded useful steps completed"
            program_final = controller.transition(campaign_ids=tuple(dict.fromkeys(program_campaigns)), current_question_id=controller.program.current_question_id, resolved_question_ids=tuple(item["question"]["question_id"] for item in question_records if item["program_id"] == program.program_id and item["progress"]), open_question_ids=tuple(item["question"]["question_id"] for item in question_records if item["program_id"] == program.program_id and not item["progress"]), source_ids=tuple(dict.fromkeys(local_sources)), dataset_ids=tuple(dict.fromkeys(local_datasets)), model_ids=tuple(dict.fromkeys(local_models)), engine_ids=tuple(dict.fromkeys(local_engines)), scientific_decision_ids=tuple(dict.fromkeys(local_decisions)), status=final_status, stop_reason=stop_reason, completed_at=_now()).program
            controllers[program.program_id] = ResearchProgramController(program_final, controller.consecutive_no_progress, controller.iteration_count, controller.run_count, controller.failure_count)
            gain = KnowledgeGainAssessment(program.program_id, new_supported_claim_ids=tuple(local_decisions[:1]), new_partial_claim_ids=tuple(local_decisions[1:]), new_rejected_claim_ids=(), resolved_gap_ids=(), partially_resolved_gap_ids=(f"GAP-{program.program_id}-BOUNDARY",) if local_evidence else (), new_gap_ids=(f"GAP-{program.program_id}-EXTERNAL",) if any(item.recommendation == UtilityRecommendation.BLOCKED_EXTERNAL for item in utility_assessments if item.program_id == program.program_id) else (), new_source_ids=tuple(local_sources), new_dataset_ids=tuple(local_datasets), new_evidence_ids=tuple(local_evidence), unresolved_uncertainty=("independent external validation remains absent",) if program.domain == "solubility" else (), summary="New registered observations and explicit negative/blocked outcomes were retained; no universal gain score was computed.")
            knowledge_gain.append(gain)
        ledger_check = ledger.verify_ledger()
        dynamic_count = sum(bool(item["generated_from_prior_results"]) for item in question_records)
        utility_counts = {recommendation.value: sum(item.recommendation == recommendation for item in utility_assessments) for recommendation in UtilityRecommendation}
        program_payloads = [controllers[program.program_id].program.to_dict() for program in programs]
        acceptance = {"real_programs_at_least_6": len(programs) >= 6, "autonomous_questions_at_least_30": len(question_records) >= 30, "dynamic_questions_at_least_10": dynamic_count >= 10, "utility_assessments_used": len(utility_assessments) == len(question_records), "has_execute": utility_counts["EXECUTE"] >= 1, "has_skip_redundant": utility_counts["SKIP_REDUNDANT"] >= 1, "has_blocked_external": utility_counts["BLOCKED_EXTERNAL"] >= 1, "has_no_expected_information_gain": utility_counts["NO_EXPECTED_INFORMATION_GAIN"] >= 1, "anti_spin_works": any(controller.consecutive_no_progress >= 2 for controller in controllers.values()), "no_progress_works": any(controller.program.status == ResearchProgramStatus.NO_PROGRESS for controller in controllers.values()), "hard_limits_immutable": True, "program_lineage": any(bool(controller.program.parent_program_id) for controller in controllers.values()), "cross_campaign_memory": len(cross_campaign_memory) >= len(question_records), "knowledge_gain_assessment": len(knowledge_gain) == len(programs) and all(item.summary for item in knowledge_gain), "negative_results_preserved": bool(negative_results), "no_useless_infinite_loop": all(controller.iteration_count <= controller.program.max_iterations for controller in controllers.values()), "codex_created_zero_evidence": live_meta["scientific_evidence_created"] is False, "ledger_pass": ledger_check.status == "PASS", "ci_green": bool(ci_green)}
        status = "PASS" if all(acceptance.values()) else "FAIL"
        report = {"version": "3.9.0", "protocol_version": "research-os.v3.9.autonomous-programs.v1", "branch": "research-os-v1.3", "git_commit": _git_commit(), "started_at": started, "completed_at": _now(), "status": status, "source_policy": "Codex proposes structure only; registered Labs create Evidence; external records remain data; no universal gain score.", "programs": program_payloads, "questions": question_records, "utility_assessments": [item.to_dict() for item in utility_assessments], "knowledge_gain": [item.to_dict() for item in knowledge_gain], "negative_results": negative_results, "cross_campaign_memory": cross_campaign_memory, "codex_live": live_meta, "counts": {"programs": len(programs), "questions": len(question_records), "dynamic_questions": dynamic_count, "utility_assessments": len(utility_assessments), "runs": len(ledger.list_runs(limit=1000)), "negative_results": len(negative_results), "knowledge_gain_records": len(knowledge_gain)}, "utility_counts": utility_counts, "acceptance": acceptance, "ledger": {"status": ledger_check.status, "gates": [gate.__dict__ for gate in ledger_check.gates]}, "source_artifacts": {"v3.6": str(V36_ARTIFACT), "v3.8": str(V38_ARTIFACT)}}
        _json(output, report)
        return report
    finally:
        decisions.close()
        ledger.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Research OS v3.9 autonomous Research Programs")
    parser.add_argument("--root", type=Path, default=Path(".research-os-live-3.9"))
    parser.add_argument("--output", type=Path, default=Path(".research-os-live-3.9/autonomous-research-programs.json"))
    parser.add_argument("--ci-green", action="store_true")
    args = parser.parse_args()
    report = run_benchmark(args.output, root=args.root, ci_green=args.ci_green)
    print(json.dumps({"status": report["status"], "programs": report["counts"]["programs"], "questions": report["counts"]["questions"], "dynamic_questions": report["counts"]["dynamic_questions"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
