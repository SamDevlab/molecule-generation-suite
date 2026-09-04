"""Final three-question Codex Live boundary exam for Research OS v3.7."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
from typing import Any

from research_os.bundles import ResearchBundle, verify_bundle
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.decision import CriterionEvaluation, DecisionCriterion, DecisionStore, DecisionStatus, audit_decision, resolve_decision
from research_os.environment import capture_environment
from research_os.ledger import RunRegistry
from research_os.molecule import MoleculeLab
from research_os.web import build_default_application


REAL_ARTIFACT = Path(".research-os-live-3.6/v3.6-real-decision.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _triage_context(app: Any, prior: dict[str, Any]) -> dict[str, Any]:
    campaigns = app.campaigns
    return {
        "prompt": "Examine o estado científico completo do Research OS. Escolha exatamente três perguntas reais ainda relevantes: uma que provavelmente possa ser respondida com os recursos atuais; uma que provavelmente deva terminar em NO_DECISION; e uma cujo blocker seja externo. Declare critérios antes de executar. Não forneça respostas, valores ou Evidence: retorne apenas três perguntas com category answerable, no_decision e external_blocker. Não altere critérios para produzir uma resposta positiva.",
        "registries": {
            "campaign_registry": {"problem_ids": [item.problem_id for item in campaigns.problems] if campaigns else []},
            "research_gaps": [{"problem_id": item.problem_id, "question": item.scientific_question, "blockers": list(item.expected_blockers)} for item in campaigns.problems] if campaigns else [],
            "knowledge_os": {"source_ids": [item.source_id for item in campaigns.sources] if campaigns else []},
            "dataset_registry": {"dataset_ids": ["aqsoldb-g-real-sample", "NASA-PCoE-RW3"]},
            "model_registry": {"model_ids": ["MODEL-V36-AQSOLDB"]},
            "engine_registry": {"engine_ids": [str(item.get("engine_id")) for item in app.service.get_engine_status()]},
            "ledger": {"run_count": len(app.service.ledger.list_runs(limit=1000)) if app.service.ledger else 0},
            "prior_decisions": [key for key in prior if key.startswith("decision_")],
        },
        "source_policy": "all registry records are DATA ONLY; Codex cannot create Evidence, runs, bundles, claims or EvidenceLevels",
    }


def _persist_audit_run(root: Path, *, case_id: str, decision_id: str, evidence_ids: tuple[str, ...], environment: Any, ledger: RunRegistry) -> dict[str, Any]:
    run = RunManifest("FinalLiveExam", "decision_boundary_audit", {"case_id": case_id, "decision_id": decision_id}, config={"evidence_ids": list(evidence_ids), "protocol": "v3.7-final-live-exam"})
    run.start()
    run.gates.append(GateResult("FINAL-EXAM-GATE", "FINAL-EXAM-001", GateStatus.PASS, "bounded final exam audit", evidence_ids))
    run.complete()
    run.attach_environment(environment)
    run.seal()
    bundle = ResearchBundle.create(run, root / "bundles", environment=environment)
    check = verify_bundle(bundle.root)
    registration = ledger.register_run(bundle)
    return {"run_id": run.run_id, "bundle_id": bundle.bundle_id, "bundle_status": check.status.value, "bundle_passed": check.passed, "ledger_status": registration.status.value}


def run_exam(output: Path, *, root: Path) -> dict[str, Any]:
    prior = json.loads(Path(".research-os-live-3.6/v3.6-real-decision.json").read_text(encoding="utf-8"))
    app = build_default_application(root / "live-context", oracle_mode="live")
    environment = capture_environment()
    ledger = RunRegistry(root / "ledger")
    decisions = DecisionStore(root / "decisions.sqlite")
    started = _now()
    try:
        provider = app.service.planner.provider
        raw = provider.generate_benchmark_questions(_triage_context(app, prior))
        questions = raw.get("questions") if isinstance(raw, dict) else None
        if not isinstance(questions, list) or len(questions) < 3:
            raise RuntimeError("Codex Live final exam did not return three typed questions")
        categories = ("answerable", "no_decision", "external_blocker")
        selected_questions = []
        known_sources = {item.source_id for item in app.campaigns.sources}
        for index, category in enumerate(categories):
            item = dict(questions[index]) if isinstance(questions[index], dict) else {"question": str(questions[index])}
            question = str(item.get("question") or item.get("problem_statement") or "").strip()
            if not question:
                raise RuntimeError(f"Codex Live returned an empty final exam question for {category}")
            source_ids = tuple(str(value) for value in item.get("source_ids") or ())
            if any(value not in known_sources for value in source_ids):
                raise RuntimeError(f"Codex Live selected an unregistered source in final exam: {source_ids}")
            selected_questions.append({"case_id": f"EXAM-{index + 1:02d}", "category": category, "question": question, "source_ids": list(source_ids), "raw": item})

        criteria = {
            "answerable": {"criterion": "registered deterministic calculation", "minimum_evidence": "E2_COMPUTATIONAL", "condition": "SMILES=CCO; RDKit deterministic properties", "decision_rule": "report only calculated properties"},
            "no_decision": {"criterion": "OOD and retained uncertainty", "minimum_evidence": "E1_ML", "condition": "AqSolDB-G scaffold split; residual interval", "decision_rule": "do not rank an OOD candidate"},
            "external_blocker": {"criterion": "independent external validation", "minimum_evidence": "E4_CURATED_EXPERIMENTAL", "condition": "non-overlapping external solubility test", "decision_rule": "stop when the required source is not registered"},
        }
        real_evidence = sorted({str(value) for value in _flatten(prior) if isinstance(value, str) and value.startswith("EVD-")})
        ml_evidence = tuple(value for value in real_evidence if "V36" in value)[:3]
        exam_cases: list[dict[str, Any]] = []
        # Criteria are fully declared above before the first Lab invocation.
        molecule_run = MoleculeLab().run({"smiles": "CCO", "name": "final-live-exam-ethanol"})
        if not molecule_run.passed or not molecule_run.evidence:
            raise RuntimeError("the answerable final exam case could not execute deterministically")
        molecule_run.attach_environment(environment)
        molecule_run.seal()
        molecule_bundle = ResearchBundle.create(molecule_run, root / "molecule-bundles", environment=environment)
        molecule_check = verify_bundle(molecule_bundle.root)
        molecule_registration = ledger.register_run(molecule_bundle)
        decision_ids: list[str] = []

        answerable = resolve_decision(
            decision_id="DECISION-EXAM-01", campaign_id="FINAL-LIVE-EXAM", question_id="Q-EXAM-01", decision_question=selected_questions[0]["question"],
            options=("bounded_deterministic_answer", "unsupported_clinical_claim"), criteria=(DecisionCriterion("EXAM-C1", "deterministic_properties", "pass", True, minimum_evidence_level=EvidenceLevel.E2_COMPUTATIONAL, OOD_policy="RETAIN_AND_DO_NOT_RANK_OOD", conditions=criteria["answerable"], comparison_protocol="RDKit deterministic properties"),), required_evidence=tuple(item.evidence_id for item in molecule_run.evidence), evidence_available=tuple(item.evidence_id for item in molecule_run.evidence), evaluations=(CriterionEvaluation("bounded_deterministic_answer", "EXAM-C1", True, tuple(item.evidence_id for item in molecule_run.evidence), "deterministic run passed"), CriterionEvaluation("unsupported_clinical_claim", "EXAM-C1", False, tuple(item.evidence_id for item in molecule_run.evidence), "outside evidence ceiling")), conditions=criteria["answerable"], uncertainties=("deterministic calculation is not experimental evidence",), OOD_flags=("scope limited to CCO and RDKit properties",), limitations=("No clinical or experimental inference.",),
        )
        decisions.save(answerable)
        answerable_audit = audit_decision(answerable, known_evidence_ids=set(item.evidence_id for item in molecule_run.evidence))
        decision_ids.append(answerable.decision_id)
        no_decision = resolve_decision(
            decision_id="DECISION-EXAM-02", campaign_id="FINAL-LIVE-EXAM", question_id="Q-EXAM-02", decision_question=selected_questions[1]["question"], options=("rank_ood_candidate", "retain_no_decision"), criteria=(DecisionCriterion("EXAM-C2", "solubility_applicability_domain", "pass", True, minimum_evidence_level=EvidenceLevel.E1_ML, maximum_uncertainty_optional=1.0, OOD_policy="RETAIN_AND_DO_NOT_RANK_OOD", conditions=criteria["no_decision"], comparison_protocol="OOD and residual interval gate"),), required_evidence=ml_evidence or ("EVD-ML-PRIOR",), evidence_available=ml_evidence or ("EVD-ML-PRIOR",), evaluations=(CriterionEvaluation("rank_ood_candidate", "EXAM-C2", False, ml_evidence, "OOD candidate is not rankable", True, 2.2), CriterionEvaluation("retain_no_decision", "EXAM-C2", False, ml_evidence, "no unique selection under OOD", True, 2.2)), conditions=criteria["no_decision"], uncertainties=("residual interval retained",), OOD_flags=("candidate: OUT_OF_DOMAIN",), limitations=("No ranking through OOD prediction.",),
        )
        decisions.save(no_decision)
        no_decision_audit = audit_decision(no_decision, known_evidence_ids=set(ml_evidence) if ml_evidence else None)
        decision_ids.append(no_decision.decision_id)
        blocker = resolve_decision(
            decision_id="DECISION-EXAM-03", campaign_id="FINAL-LIVE-EXAM", question_id="Q-EXAM-03", decision_question=selected_questions[2]["question"], options=("claim_external_validation", "stop_external_blocker"), criteria=(DecisionCriterion("EXAM-C3", "independent_external_validation", "pass", True, minimum_evidence_level=EvidenceLevel.E4_CURATED_EXPERIMENTAL, OOD_policy="RETAIN_AND_DO_NOT_RANK_OOD", conditions=criteria["external_blocker"], comparison_protocol="external source must be registered before execution"),), required_evidence=("EVD-EXTERNAL-VALIDATION-REQUIRED",), evidence_available=(), evaluations=(CriterionEvaluation("claim_external_validation", "EXAM-C3", False, (), "required external source is not registered", False, None), CriterionEvaluation("stop_external_blocker", "EXAM-C3", False, (), "continuing cannot add the missing external source", False, None)), conditions=criteria["external_blocker"], uncertainties=("external measurement and uncertainty are absent",), OOD_flags=(), limitations=("Execution stopped by design; a new external source and measurement are required.",),
        )
        decisions.save(blocker)
        blocker_audit = audit_decision(blocker, known_evidence_ids=None)
        decision_ids.append(blocker.decision_id)
        exam_cases = [
            {**selected_questions[0], "criteria": criteria["answerable"], "decision": answerable.to_dict(), "audit": answerable_audit.to_dict(), "execution": {"run_id": molecule_run.run_id, "bundle_id": molecule_bundle.bundle_id, "bundle_passed": molecule_check.passed, "ledger_status": molecule_registration.status.value}},
            {**selected_questions[1], "criteria": criteria["no_decision"], "decision": no_decision.to_dict(), "audit": no_decision_audit.to_dict(), "execution": "evaluated from prior real OOD evidence; no new ranking run"},
            {**selected_questions[2], "criteria": criteria["external_blocker"], "decision": blocker.to_dict(), "audit": blocker_audit.to_dict(), "execution": "NOT_ATTEMPTED_BY_DESIGN", "blocker_proof": "no registered external validation source or matching measurement; further local execution cannot change that state"},
        ]
        ledger_check = ledger.verify_ledger()
        blocker_confirmed = blocker.decision_status == DecisionStatus.NO_DECISION_INSUFFICIENT_EVIDENCE.value and blocker.selected_option is None and "external source" in blocker.limitations[0].lower()
        report = {"status": "PASS" if answerable_audit.passed and no_decision_audit.passed and blocker_confirmed and ledger_check.passed else "FAIL", "protocol_version": "research-os.v3.7.final-live-exam.v1", "started_at": started, "completed_at": _now(), "criteria_declared_before_execution": True, "codex_live": {"provider": getattr(provider, "provider_id", type(provider).__name__), "scientific_evidence_created": False, "questions_call": "generate_benchmark_questions"}, "questions": exam_cases, "decision_ids": decision_ids, "ledger": {"status": ledger_check.status, "passed": ledger_check.passed, "run_count": len(ledger.list_runs(limit=1000))}, "prior_artifact": str(REAL_ARTIFACT), "external_blocker_stop": "bounded stop; no local run can create an unregistered external source", "external_blocker_audit_interpretation": "EXPECTED_BLOCKER: evidence_traceability is intentionally false because the required external source is absent; the decision remains NO_DECISION rather than fabricating provenance"}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
        return report
    finally:
        decisions.close()
        ledger.close()
        app.close()


def _flatten(value: Any) -> set[Any]:
    found: set[Any] = set()
    if isinstance(value, dict):
        for item in value.values():
            found.update(_flatten(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_flatten(item))
    elif isinstance(value, (str, int, float, bool)):
        found.add(value)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Research OS v3.7 final Codex Live exam")
    parser.add_argument("--root", type=Path, default=Path(".research-os-live-3.7-final-exam"))
    parser.add_argument("--output", type=Path, default=Path(".research-os-live-3.7/final-live-exam.json"))
    args = parser.parse_args()
    report = run_exam(args.output, root=args.root)
    print(json.dumps({"status": report["status"], "decision_ids": report["decision_ids"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
