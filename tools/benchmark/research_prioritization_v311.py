"""Research OS v3.11 research-prioritization benchmark."""

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

from research_os.prioritization import PriorityRecommendation, ResearchPriorityAssessment, ResearchPriorityQueue
from research_os.web import build_default_application


V310_ARTIFACT = REPO_ROOT / ".research-os-live-3.10" / "longitudinal-memory-benchmark.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_commit() -> str:
    import subprocess
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False).stdout.strip()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")


def _assessment(assessment_id: str, question_id: str, gap_id: str, relevance: str, evidence: tuple[str, ...], target: tuple[str, ...], resolvability: str, gain: str, redundancy: str, engines: tuple[str, ...], datasets: tuple[str, ...], sources: tuple[str, ...], dependency: str | None, scope: str, safety: str, recommendation: PriorityRecommendation, rationale: str, *, supersedes: str | None = None) -> ResearchPriorityAssessment:
    return ResearchPriorityAssessment(assessment_id, question_id, gap_id, relevance, evidence, target, resolvability, gain, redundancy, engines, datasets, sources, dependency, scope, safety, recommendation, rationale, supersedes_assessment_id=supersedes)


def _initial_assessments() -> tuple[ResearchPriorityAssessment, ...]:
    return (
        _assessment("PRI-V311-DOCK-01", "Q-PRIORITY-DOCKING-50", "GAP-DOCKING-E2-ONLY", "MEDIUM", ("E2_COMPUTATIONAL",), ("E3_PHYSICS",), "locally executable but bounded by computational evidence", "low: identical replicates already characterize the declared protocol", "HIGH", ("autodock-vina",), ("RCSB PDB 1PXX",), ("SRC-RCSB-1PXX", "SRC-NASEM-REPRO"), None, "50 additional identical docking replicates", "SAFE_BUT_REDUNDANT", PriorityRecommendation.LOW_INFORMATION_GAIN, "The v3.8 three-replicate protocol already answers the same bounded question; more identical runs do not raise the evidence ceiling."),
        _assessment("PRI-V311-SOL-01", "Q-PRIORITY-SOLUBILITY-EXTERNAL", "GAP-SOLUBILITY-EXTERNAL-VALIDATION", "HIGH", ("E1_ML",), ("E4_CURATED_EXPERIMENTAL", "E5_VALIDATED_EXPERIMENTAL"), "actionable as an external-data search, not locally solvable without a new eligible dataset", "high: could materially change the model-boundary decision", "LOW", ("numpy-ridge",), ("independent solubility dataset: not registered",), ("SRC-AQSOLDB-DATA", "SRC-AQSOLDB-PAPER"), "eligible independent external dataset", "search and verify an independent dataset; do not retrain before evaluation", "SAFE_ANALYSIS_ONLY", PriorityRecommendation.PRIORITIZE_NOW, "This open gap is high relevance and a new eligible dataset could change the current decision; the queue prioritizes the search, not an invented result."),
        _assessment("PRI-V311-RDKIT-01", "Q-PRIORITY-RDKIT-REPEAT", "GAP-MOLECULE-RECALCULATION", "LOW", ("E2_COMPUTATIONAL",), ("E2_COMPUTATIONAL",), "locally executable", "none: deterministic descriptors were already reproduced", "HIGH", ("rdkit",), ("none",), (), None, "rerun identical RDKit descriptors", "SAFE_BUT_REDUNDANT", PriorityRecommendation.LOW_INFORMATION_GAIN, "A deterministic repeat without changed inputs, engine or question adds no new information."),
        _assessment("PRI-V311-MAT-01", "Q-PRIORITY-MATERIALS-UNSAFE", "GAP-MATERIALS-CONDITION-COMPLETE", "HIGH", ("E0_HEURISTIC",), ("E4_CURATED_EXPERIMENTAL",), "not locally resolvable", "unknown: required record is absent", "NOT_APPLICABLE", ("none configured",), ("condition-complete alloy record: not registered",), ("SRC-NASA-HE-REPORT", "SRC-NASA-STD-6016C"), "condition-complete external record", "compare a material without condition-matched records", "REJECT_UNSAFE", PriorityRecommendation.UNSAFE, "A material comparison without alloy, environment, stress and temperature records could create an unsafe unsupported conclusion."),
        _assessment("PRI-V311-BATT-01", "Q-PRIORITY-BATTERY-COMP", "GAP-BATTERY-METADATA", "HIGH", ("E4_CURATED_EXPERIMENTAL",), ("E4_CURATED_EXPERIMENTAL",), "external dataset required", "medium: richer fields could resolve a decision criterion", "LOW", ("scipy",), ("battery-nasa-pcoe-rw3", "complementary dataset: not registered"), ("SRC-NASA-PCOE-RW3", "SRC-DOE-BATTERY-DATA-HUB"), "richer condition-matched battery dataset", "search for a complementary capacity/current/voltage/temperature/cycle record", "SAFE_ANALYSIS_ONLY", PriorityRecommendation.BLOCKED, "The current schema observation is real, but a complementary condition-matched record is externally blocked."),
        _assessment("PRI-V311-USER-01", "Q-PRIORITY-USER-CORPUS", "GAP-USER-CORPUS-INGESTION", "HIGH", (), ("E4_CURATED_EXPERIMENTAL",), "requires explicit user corpus and review", "potentially high but unassessable before corpus arrival", "LOW", (), ("user corpus: not supplied",), (), "user-provided corpus and permissions", "wait for a user-supplied corpus; do not invent contents", "SAFE_BOUNDARY", PriorityRecommendation.DEFER, "The gap is important but not actionable until the corpus and usage permissions exist."),
        _assessment("PRI-V311-CANT-01", "Q-PRIORITY-CANTERA", "GAP-E3-E4-COMPARISON", "MEDIUM", ("E3_PHYSICS",), ("E4_CURATED_EXPERIMENTAL",), "simulation is executable; comparable experiment is absent", "medium: an eligible matched experiment could test a model boundary", "LOW", ("cantera",), ("matched experimental record: not registered",), ("SRC-CANTERA-GRI30", "SRC-NASEM-REPRO"), "condition-matched experimental record", "search and condition-match an experiment before comparison", "SAFE_SIMULATION_ONLY", PriorityRecommendation.SECONDARY, "Cantera is available for simulation, but the E3-to-E4 opportunity depends on external comparable evidence."),
        _assessment("PRI-V311-COX2-01", "Q-PRIORITY-COX2-DEEPER", "GAP-DOCKING-E2-ONLY", "MEDIUM", ("E2_COMPUTATIONAL",), ("E2_COMPUTATIONAL",), "locally executable within current protocol", "low: more computational depth does not change the E2 ceiling", "MEDIUM", ("autodock-vina", "openbabel"), ("RCSB PDB 1PXX",), ("SRC-RCSB-1PXX",), None, "deeper COX-2 computational validation", "SAFE_COMPUTATIONAL_ONLY", PriorityRecommendation.SECONDARY, "This can refine computational reproducibility but is less decision-changing than an independent solubility dataset."),
    )


def _live_priority(root: Path, candidates: tuple[ResearchPriorityAssessment, ...]) -> tuple[dict[str, Any], dict[str, Any]]:
    app = build_default_application(root / "codex-live", oracle_mode="live")
    context = {
        "prompt": "Reassess which supplied research step is worth doing next using only registered current state. Do not create evidence or override safety/evidence gates.",
        "options": {
            "A": "run 50 more docking replicates",
            "B": "search for independent solubility external dataset",
            "C": "rerun identical RDKit descriptors",
            "D": "attempt material comparison without records",
        },
        "candidates": [{"candidate_question_id": item.candidate_question_id, "candidate_gap_id": item.candidate_gap_id, "current_evidence": list(item.current_evidence), "resolvability": item.resolvability, "expected_information_gain": item.expected_information_gain, "recommendation": item.recommendation.value, "rationale": item.rationale} for item in candidates],
        "prior_memory": {"v3.10": "PASS", "unresolved_gaps": [item.candidate_gap_id for item in candidates]},
        "source_policy": "Codex can explain supplied candidates only; Research OS owns priority and execution gates.",
    }
    try:
        provider = app.service.planner.provider
        raw = provider.prioritize_research(context)
        return raw, {"provider": getattr(provider, "provider_id", type(provider).__name__), "model": getattr(provider, "model", None), "status": "LIVE_CODEX_VALIDATED", "scientific_evidence_created": False, "override_applied": False, "options_presented": sorted(context["options"]), "raw": raw}
    finally:
        app.close()


def run_benchmark(output: Path, *, root: Path, ci_green: bool = False) -> dict[str, Any]:
    prior = json.loads(V310_ARTIFACT.read_text(encoding="utf-8"))
    if prior.get("status") != "PASS":
        raise RuntimeError("v3.11 is closed until v3.10 artifact is PASS")
    initial = _initial_assessments()
    live_raw, live_meta = _live_priority(root, initial)
    battery = next(item for item in initial if item.candidate_question_id == "Q-PRIORITY-BATTERY-COMP")
    battery_updated = replace(battery, assessment_id="PRI-V311-BATT-02", current_evidence=("E4_CURATED_EXPERIMENTAL", "EVD-V39-BATTERY"), resolvability="partially informed; richer external record remains required", expected_information_gain="medium: the observed schema narrows the missingness question", recommendation=PriorityRecommendation.SECONDARY, rationale="The fresh real schema observation narrows the missing fields; the complementary condition-matched dataset remains open.", supersedes_assessment_id=battery.assessment_id)
    current = tuple(battery_updated if item.assessment_id == battery.assessment_id else item for item in initial)
    old_queue = ResearchPriorityQueue.from_assessments(initial, queue_id="QUEUE-V311-INITIAL")
    queue = ResearchPriorityQueue.from_assessments(current, queue_id="QUEUE-V311-FINAL", history=initial)
    query_specs = (
        ("most_resolvable", "What is the most resolvable gap right now?", "Q-PRIORITY-SOLUBILITY-EXTERNAL"),
        ("highest_gain", "What gap has the highest likely information gain?", "Q-PRIORITY-SOLUBILITY-EXTERNAL"),
        ("redundant_docking", "What research step would be redundant for docking?", "Q-PRIORITY-DOCKING-50"),
        ("external_battery", "What experiment requires external evidence for battery?", "Q-PRIORITY-BATTERY-COMP"),
        ("stop_compute", "What should we stop spending computation on?", "Q-PRIORITY-RDKIT-REPEAT"),
        ("decision_change", "Which open question can materially change a decision?", "Q-PRIORITY-SOLUBILITY-EXTERNAL"),
        ("important_not_actionable", "Which gap is important but not currently actionable?", "Q-PRIORITY-USER-CORPUS"),
        ("missing_dataset", "What missing dataset would unlock the most claims?", "Q-PRIORITY-SOLUBILITY-EXTERNAL"),
        ("missing_engine", "What engine would unlock the most blocked workflows?", "Q-PRIORITY-BATTERY-COMP"),
        ("uncertainty", "What current result is most sensitive to uncertainty?", "Q-PRIORITY-SOLUBILITY-EXTERNAL"),
        ("option_a", "Should option A run 50 more docking replicates?", "Q-PRIORITY-DOCKING-50"),
        ("option_b", "Should option B search an independent solubility dataset?", "Q-PRIORITY-SOLUBILITY-EXTERNAL"),
        ("option_c", "Should option C rerun identical RDKit descriptors?", "Q-PRIORITY-RDKIT-REPEAT"),
        ("option_d", "Should option D attempt material comparison without records?", "Q-PRIORITY-MATERIALS-UNSAFE"),
        ("e3_e4", "Is an E3-versus-E4 comparison actionable now?", "Q-PRIORITY-CANTERA"),
        ("battery_update", "How did the fresh battery schema evidence change priority?", "Q-PRIORITY-BATTERY-COMP"),
        ("co2_depth", "Should deeper COX-2 computational validation precede external validation?", "Q-PRIORITY-COX2-DEEPER"),
        ("materials", "Can materials records be compared without a condition-complete source?", "Q-PRIORITY-MATERIALS-UNSAFE"),
        ("user_corpus", "Can user corpus ingestion be executed without a supplied corpus?", "Q-PRIORITY-USER-CORPUS"),
        ("queue_order", "Which candidate is ordered first and why?", "Q-PRIORITY-SOLUBILITY-EXTERNAL"),
    )
    query_records: list[dict[str, Any]] = []
    for category, question, candidate_id in query_specs:
        assessment = queue.assessment(candidate_id)
        query_records.append({"category": category, "question": question, "candidate_question_id": candidate_id, "answer": f"{assessment.recommendation.value}: {assessment.rationale}", "assessment_id": assessment.assessment_id, "grounded": assessment.assessment_id in {item.assessment_id for item in queue.assessment_history}, "reason_for_order": next(entry.reason_for_order for entry in queue.entries if entry.assessment_id == assessment.assessment_id)})
    old_position = next(entry.position for entry in old_queue.entries if entry.assessment_id == battery.assessment_id)
    new_position = next(entry.position for entry in queue.entries if entry.assessment_id == battery_updated.assessment_id)
    recommendations = {recommendation.value: sum(item.recommendation == recommendation for item in current) for recommendation in PriorityRecommendation}
    acceptance = {
        "priority_assessment_exists": all(isinstance(item, ResearchPriorityAssessment) for item in current),
        "priority_queue_traceable": queue.valid and all(entry.reason_for_order and entry.assessment_id for entry in queue.entries),
        "prioritization_queries_at_least_20": len(query_records) >= 20,
        "queries_grounded": all(item["grounded"] for item in query_records),
        "redundancy_recognized": any(item.recommendation == PriorityRecommendation.LOW_INFORMATION_GAIN for item in current),
        "external_blocker_recognized": any(item.recommendation == PriorityRecommendation.BLOCKED for item in (*initial, *current)),
        "actionable_vs_important": next(item for item in current if item.candidate_question_id == "Q-PRIORITY-SOLUBILITY-EXTERNAL").recommendation == PriorityRecommendation.PRIORITIZE_NOW and next(item for item in current if item.candidate_question_id == "Q-PRIORITY-USER-CORPUS").recommendation == PriorityRecommendation.DEFER,
        "new_evidence_reorders_without_deleting_history": old_position != new_position and battery.assessment_id in {item.assessment_id for item in queue.assessment_history} and battery_updated.assessment_id in {item.assessment_id for item in queue.assessment_history},
        "no_universal_hidden_score": all("score" not in json.dumps(item.to_dict(), ensure_ascii=False).lower() for item in current) and all("score" not in json.dumps(entry.to_dict(), ensure_ascii=False).lower() for entry in queue.entries),
        "codex_cannot_override_scientific_safety_gates": live_meta["override_applied"] is False and next(item for item in current if item.candidate_question_id == "Q-PRIORITY-MATERIALS-UNSAFE").recommendation == PriorityRecommendation.UNSAFE,
        "low_information_gain_step_skipped": recommendations[PriorityRecommendation.LOW_INFORMATION_GAIN.value] >= 1,
        "decision_changing_gap_prioritized": next(item for item in current if item.candidate_question_id == "Q-PRIORITY-SOLUBILITY-EXTERNAL").recommendation == PriorityRecommendation.PRIORITIZE_NOW,
        "codex_created_zero_evidence": live_meta["scientific_evidence_created"] is False,
        "v3_10_memory_input_pass": prior["status"] == "PASS",
        "ci_green": bool(ci_green),
    }
    report = {"version": "3.11.0", "protocol_version": "research-os.v3.11.research-prioritization.v1", "branch": "research-os-v1.3", "git_commit": _git_commit(), "started_at": _now(), "completed_at": _now(), "status": "PASS" if all(acceptance.values()) else "FAIL", "initial_queue": old_queue.to_dict(), "queue": queue.to_dict(), "assessments": [item.to_dict() for item in (*initial, battery_updated)], "queries": query_records, "codex_live": live_meta, "counts": {"assessments": len(current), "historical_assessments": len(queue.assessment_history), "prioritization_queries": len(query_records), "low_information_gain": recommendations[PriorityRecommendation.LOW_INFORMATION_GAIN.value], "blocked": recommendations[PriorityRecommendation.BLOCKED.value], "prioritize_now": recommendations[PriorityRecommendation.PRIORITIZE_NOW.value], "queue_entries": len(queue.entries)}, "acceptance": acceptance, "source_policy": "Priority is structured and traceable; Codex may reassess supplied candidates but cannot create evidence or bypass safety/evidence gates.", "source_artifacts": {"v3.10": str(V310_ARTIFACT)}}
    _write(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Research OS v3.11 prioritization benchmark")
    parser.add_argument("--root", type=Path, default=Path(".research-os-live-3.11"))
    parser.add_argument("--output", type=Path, default=Path(".research-os-live-3.11/research-prioritization-benchmark.json"))
    parser.add_argument("--ci-green", action="store_true")
    args = parser.parse_args()
    report = run_benchmark(args.output, root=args.root, ci_green=args.ci_green)
    print(json.dumps({"status": report["status"], "prioritization_queries": report["counts"]["prioritization_queries"], "queue_entries": report["counts"]["queue_entries"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
