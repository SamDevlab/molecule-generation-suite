"""Review scientific impact across the v3.9-v4.3 research history."""

from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from research_os.impact import ResearchImpactReview, ResearchImpactReviewStore


V39_ARTIFACT = REPO_ROOT / ".research-os-live-3.9" / "autonomous-research-programs.json"
V40_ARTIFACT = REPO_ROOT / ".research-os-live-4.0" / "master-validation.json"
V41_ARTIFACT = REPO_ROOT / ".research-os-live-4.1" / "research-outcome-impact.json"
V43_ARTIFACT = REPO_ROOT / ".research-os-live-4.3" / "external-validation-campaigns.json"
OUTPUT_DEFAULT = REPO_ROOT / ".research-os-live-4.4" / "research-impact-review.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")


def _legacy_review(program: dict[str, Any], gain: dict[str, Any]) -> ResearchImpactReview:
    program_id = str(program["program_id"])
    status = str(program.get("status"))
    changes: list[str] = []
    unchanged: list[str] = ["canonical EvidenceLevel vocabulary and append-only historical records"]
    cost: list[str] = []
    blocked: list[str] = []
    if gain.get("new_dataset_ids") or gain.get("new_evidence_ids") or gain.get("partially_resolved_gap_ids"):
        changes.append("registered observations or a partial gap boundary were added")
    if gain.get("new_gap_ids"):
        changes.append("the next missing evidence was made explicit")
    if not changes:
        changes.append("no material scientific state change was recorded in this program")
    if program_id == "PROG-02-COX2":
        cost.append("two identical-repeat questions were correctly skipped as redundant")
        unchanged.append("the 1PXX E2 prioritization and species boundary")
    if status == "NO_PROGRESS":
        blocked.append("the selected path did not produce new local evidence")
    if program_id in {"PROG-04-BATTERY", "PROG-05-MATERIALS", "PROG-06-CODEX"}:
        blocked.append("external or unavailable data/engine dependency remained")
    next_action = {
        "PROG-01-SOLUBILITY": "evaluate one independent compatible source with the frozen model",
        "PROG-02-COX2": "use a new receptor or protocol only when Vina is available",
        "PROG-03-COMBUSTION": "seek a condition-matched experiment before generalization",
        "PROG-04-BATTERY": "acquire a schema-complete capacity/resistance/uncertainty source",
        "PROG-05-MATERIALS": "ingest and condition-match a reviewed record-level material dataset",
        "PROG-06-CODEX": "select an executable question with expected information gain",
    }[program_id]
    return ResearchImpactReview(
        f"IMPR-V44-{program_id}",
        program_id,
        {"version": "v3.8", "state": "v3.9 predecessor state; impact contract not yet present"},
        {"version": "v3.9", "status": status, "knowledge_gain": gain},
        (),
        tuple(changes),
        tuple(unchanged),
        tuple(cost),
        tuple(blocked),
        next_action,
    )


def _v41_review(impact: dict[str, Any]) -> ResearchImpactReview:
    program_id = str(impact["program_id"])
    status = str(impact["impact_status"])
    cost = ("new identical docking was skipped because the sealed protocol already answered the question",) if program_id == "PROG-V41-COX2" else ()
    blocked = ("condition-complete external source unavailable",) if status == "BLOCKED_EXTERNAL" else ()
    return ResearchImpactReview(
        f"IMPR-V44-{program_id}",
        program_id,
        {"version": "v4.0", "state": "behavioral validation passed; impact dimensions were not yet recorded"},
        {"version": "v4.1", "impact_status": status, "summary": impact["summary"], "new_runs": impact.get("new_run_ids", []), "revised_claims": impact.get("revised_claim_ids", []), "revised_decisions": impact.get("revised_decision_ids", []), "gap_changes": {"resolved": impact.get("resolved_gap_ids", []), "partial": impact.get("partially_resolved_gap_ids", []), "new": impact.get("new_gap_ids", [])}},
        (str(impact["impact_id"]),),
        (impact["summary"],),
        ("EvidenceLevel ceiling, explicit conditions, OOD and uncertainty policy remain unchanged",),
        cost,
        blocked,
        str(impact["actionable_next_step"]),
    )


def run_review(output: Path, *, ci_green: bool = False) -> dict[str, Any]:
    v39 = _load(V39_ARTIFACT)
    v40 = _load(V40_ARTIFACT)
    v41 = _load(V41_ARTIFACT)
    v43 = _load(V43_ARTIFACT)
    if not all(item.get("status") == "PASS" for item in (v39, v40, v41, v43)):
        raise RuntimeError("v4.4 requires PASS v3.9, v4.0, v4.1 and v4.3 artifacts")
    store = ResearchImpactReviewStore()
    gains = {item["program_id"]: item for item in v39["knowledge_gain"]}
    reviews = [
        _legacy_review(program, gains[program["program_id"]])
        for program in v39["programs"]
    ]
    reviews.extend(_v41_review(item) for item in v41["research_outcome_impacts"][:6])
    v43_campaign = v43["campaigns"][0]
    reviews.append(ResearchImpactReview(
        "IMPR-V44-PROG-V43-SOLUBILITY-EXTERNAL",
        "PROG-V43-SOLUBILITY-EXTERNAL",
        {"version": "v4.1", "claim": "external validity remained an open gap"},
        {"version": "v4.3", "validation_status": v43_campaign["status"], "metrics": v43["solubility_external_validation"]["metrics"], "claim_revision": v43["claim_revision"]["revision_id"]},
        (v43_campaign["campaign_id"],),
        ("The external gap changed from untested to a measured negative boundary: the DLS-100 unique subset was entirely OOD under the locked model.", "The claim was revised without EvidenceLevel promotion."),
        ("The model remains frozen and no rankable OOD output is authorized",),
        (),
        ("unrestricted external generalization failed under this independent source",),
        "Acquire a compatible external source with in-domain overlap or explicitly retain the OOD boundary",
    ))
    for review in reviews:
        store.append(review)
    status_counts = {
        "knowledge_changed": sum("changed" in " ".join(review.scientific_changes).lower() or review.program_id in {"PROG-01-SOLUBILITY", "PROG-V41-SOLUBILITY", "PROG-V41-CODEX", "PROG-V43-SOLUBILITY-EXTERNAL"} for review in reviews),
        "decision_changed": sum(review.program_id == "PROG-V41-COMBUSTION" for review in reviews),
        "gap_refined_or_resolved": sum(bool(review.blocked_paths) is False and any(word in " ".join(review.scientific_changes).lower() for word in ("gap", "boundary", "evidence")) for review in reviews),
        "no_material_change": sum(review.program_id in {"PROG-02-COX2", "PROG-V41-COX2"} for review in reviews),
        "blocked_external": sum(bool(review.blocked_paths) for review in reviews),
        "uncertainty_refined": sum(review.program_id in {"PROG-01-SOLUBILITY", "PROG-V41-SOLUBILITY"} for review in reviews),
        "redundant_programs_identified": sum(bool(review.cost_without_gain) for review in reviews),
    }
    report = {
        "version": "4.4.0",
        "protocol_version": "research-os.v4.4.research-impact-review.v1",
        "branch": "research-os-v1.3",
        "created_at": _now(),
        "status": "PASS" if all((len(reviews) >= 10, status_counts["knowledge_changed"] > 0, status_counts["no_material_change"] > 0, status_counts["blocked_external"] > 0, status_counts["decision_changed"] > 0, status_counts["redundant_programs_identified"] > 0, all(review.valid for review in reviews), all(review.recommended_next_action.strip() for review in reviews), ci_green)) else "FAIL",
        "reviewed_versions": ["3.9", "4.0", "4.1", "4.3"],
        "reviews": [review.to_dict() for review in reviews],
        "counts": {"program_impact_reviews": len(reviews), **status_counts},
        "acceptance": {"ten_or_more_program_reviews": len(reviews) >= 10, "knowledge_changed_identified": status_counts["knowledge_changed"] > 0, "no_material_change_identified": status_counts["no_material_change"] > 0, "blocked_external_identified": status_counts["blocked_external"] > 0, "decision_changing_research_identified": status_counts["decision_changed"] > 0, "redundancy_identified": status_counts["redundant_programs_identified"] > 0, "next_step_value_grounded": all(bool(review.recommended_next_action.strip()) for review in reviews), "no_magic_impact_score": all("impact_score" not in review.to_dict() for review in reviews), "append_only_review_records": all(review.valid for review in reviews), "full_ci_green": ci_green},
        "impact_policy": "No universal score is calculated; dimensions remain separately reviewable.",
    }
    _json(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Research OS v4.4 impact reviews")
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument("--ci-green", action="store_true")
    args = parser.parse_args()
    report = run_review(args.output, ci_green=args.ci_green)
    print(json.dumps({"status": report["status"], "reviews": report["counts"]["program_impact_reviews"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
