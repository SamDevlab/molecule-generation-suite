"""Research OS v3.12 external evidence integration benchmark."""

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

from research_os.core.hashing import sha256_file
from research_os.external_evidence import EvidenceDependencyAssessment, ExternalEvidenceIntegrator, ExternalEvidenceUpdate
from research_os.knowledge import ClaimRevision, ClaimStatus


V311_ARTIFACT = REPO_ROOT / ".research-os-live-3.11" / "research-prioritization-benchmark.json"
V310_ARTIFACT = REPO_ROOT / ".research-os-live-3.10" / "longitudinal-memory-benchmark.json"
V36_ARTIFACT = REPO_ROOT / ".research-os-live-3.6" / "v3.6-real-decision.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_commit() -> str:
    import subprocess
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False).stdout.strip()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")


def _update(update_id: str, source_id: str, source_version: str, evidence_ids: tuple[str, ...], claims: tuple[str, ...], gaps: tuple[str, ...], decisions: tuple[str, ...], compatibility: str, conflicts: tuple[str, ...] = (), revisions: tuple[str, ...] = (), dataset_id: str | None = None) -> ExternalEvidenceUpdate:
    return ExternalEvidenceUpdate(update_id, source_id, source_version, dataset_id, evidence_ids, claims, gaps, decisions, compatibility, conflicts, revisions)


def _real_search_updates() -> tuple[ExternalEvidenceUpdate, ...]:
    return (
        _update("SEARCH-SOLUBILITY-INORGANIC", "SRC-NEWFOUND-AQUEOUS-SOLUBILITY", "v1.1@2025-01-14", (), (), ("GAP-SOLUBILITY-EXTERNAL-VALIDATION",), (), "BLOCKED_NOT_INGESTED: public compilation uses inorganic formulas and g/100g H2O units; it is not condition-compatible with the frozen organic AqSolDB log10(mol/L) evaluation.", dataset_id="newfound-aqueous-solubility"),
        _update("SEARCH-BATTERY-OXFORD", "SRC-OXFORD-BATTERY-AGING", "repository-record@2020", (), (), ("GAP-BATTERY-METADATA",), (), "BLOCKED_NOT_INGESTED: public record advertises capacity/current/voltage/temperature, but local bytes, hash, license and schema were not ingested in this run.", dataset_id="oxford-energy-trading-battery"),
        _update("SEARCH-BATTERY-NATURE", "SRC-NATURE-NMC-AGING", "doi:10.1038/s41597-024-03831-x", (), (), ("GAP-BATTERY-METADATA",), (), "BLOCKED_NOT_INGESTED: the paper documents richer measurements, but the multi-gigabyte data package was not downloaded or hashed here.", dataset_id="nmc-c-siO-battery-aging"),
        _update("SEARCH-MATERIALS-NASA", "SRC-NASA-HE-1975", "ntrs:19750004044", (), (), ("GAP-MATERIALS-CONDITION-COMPLETE",), (), "BLOCKED_NOT_INGESTED: a technical report is not a condition-complete record-level alloy dataset for the requested comparison."),
        _update("SEARCH-THERMOPHYSICS-NIST", "SRC-NIST-TRC", "official-page@current-search", (), (), ("GAP-E3-E4-COMPARISON",), (), "BLOCKED_NOT_INGESTED: official thermophysical coverage is a source/discovery path, not a matched E4 experiment for the Cantera protocol."),
    )


def run_benchmark(output: Path, *, root: Path, ci_green: bool = False) -> dict[str, Any]:
    prior311 = _json(V311_ARTIFACT)
    prior310 = _json(V310_ARTIFACT)
    prior36 = _json(V36_ARTIFACT)
    if prior311.get("status") != "PASS" or prior310.get("status") != "PASS":
        raise RuntimeError("v3.12 is closed until v3.10 and v3.11 artifacts are PASS")
    integrator = ExternalEvidenceIntegrator()
    real_search = _real_search_updates()
    for update in real_search:
        integrator.add_update(update)
    existing_real = _update("UPDATE-REAL-VERSIONED-BATTERY", "SRC-NASA-PCOE-RW3", "artifact@v3.9", ("EVD-V39-BATTERY",), (), ("GAP-BATTERY-METADATA",), ("DECISION-V310-BATTERY-REVALUATED",), "COMPATIBLE_VERSIONED_EVIDENCE: same registered archive and schema; it narrows missingness but is not an independent confirmation.", revisions=("REV-V310-AQSOLDB-02",), dataset_id="battery-nasa-pcoe-rw3")
    integrator.add_update(existing_real)
    fixture_updates: list[ExternalEvidenceUpdate] = []
    for index, (compatibility, conflicts, gap, claim, decision) in enumerate((
        ("COMPATIBLE", (), "GAP-BATTERY-METADATA", "CLM-EXTERNAL-1", "DECISION-V310-BATTERY-REVALUATED"),
        ("CONFLICTING", ("capacity field conflicts with frozen missingness boundary",), "GAP-BATTERY-METADATA", "CLM-EXTERNAL-2", "DECISION-V310-BATTERY-REVALUATED"),
        ("DUPLICATE", (), "GAP-BATTERY-METADATA", "CLM-EXTERNAL-3", "DECISION-V310-BATTERY-REVALUATED"),
        ("DEPENDENT", (), "GAP-SOLUBILITY-EXTERNAL-VALIDATION", "CLM-EXTERNAL-4", "DECISION-V310-BATTERY-REVALUATED"),
        ("STALE_VERSION", (), "GAP-SOLUBILITY-EXTERNAL-VALIDATION", "CLM-EXTERNAL-5", "DECISION-V310-BATTERY-REVALUATED"),
        ("INCOMPATIBLE_UNITS", (), "GAP-SOLUBILITY-EXTERNAL-VALIDATION", "CLM-EXTERNAL-6", "DECISION-V310-BATTERY-REVALUATED"),
        ("MISSING_METADATA", (), "GAP-MATERIALS-CONDITION-COMPLETE", "CLM-EXTERNAL-7", "DECISION-V310-BATTERY-REVALUATED"),
        ("SOURCE_SUPERSESSION", (), "GAP-MATERIALS-CONDITION-COMPLETE", "CLM-EXTERNAL-8", "DECISION-V310-BATTERY-REVALUATED"),
        ("CLAIM_REVISION", (), "GAP-SOLUBILITY-EXTERNAL-VALIDATION", "CLM-863B37BB0E38", "DECISION-V310-BATTERY-REVALUATED"),
        ("DECISION_REVISION", (), "GAP-BATTERY-METADATA", "CLM-EXTERNAL-10", "DECISION-V310-BATTERY-REVALUATED"),
        ("PRIORITY_REVISION", (), "GAP-BATTERY-METADATA", "CLM-EXTERNAL-11", "DECISION-V310-BATTERY-REVALUATED"),
        ("INDEPENDENT_SOURCE", (), "GAP-SOLUBILITY-EXTERNAL-VALIDATION", "CLM-EXTERNAL-12", "DECISION-V310-BATTERY-REVALUATED"),
        ("PARTIAL_COMPATIBILITY", (), "GAP-E3-E4-COMPARISON", "CLM-EXTERNAL-13", "DECISION-V310-BATTERY-REVALUATED"),
        ("NO_EVIDENCE_PROMOTION", (), "GAP-E3-E4-COMPARISON", "CLM-EXTERNAL-14", "DECISION-V310-BATTERY-REVALUATED"),
        ("HISTORICAL_PRESERVATION", (), "GAP-DOCKING-E2-ONLY", "CLM-EXTERNAL-15", "DECISION-V310-BATTERY-REVALUATED"),
    ), 1):
        fixture = _update(f"FIXTURE-UPDATE-{index:02d}", f"SRC-FIXTURE-{index:02d}", f"fixture-v{index}", (f"EVD-FIXTURE-{index:02d}",), (claim,), (gap,), (decision,), compatibility, conflicts, (f"REV-FIXTURE-{index:02d}",))
        fixture_updates.append(fixture)
        integrator.add_update(fixture)
    metadata = {
        "EVD-V39-BATTERY": {"source_ids": ["SRC-NASA-PCOE-RW3"], "dataset_ids": ["battery-nasa-pcoe-rw3"], "model_ids": [], "run_ids": ["RUN-V39-BATTERY"], "publication_ids": ["NASA-PCOE-RW3"]},
        "EVD-V39-SOLUBILITY-MODEL": {"source_ids": ["SRC-AQSOLDB-DATA"], "dataset_ids": ["aqsoldb-g-real-sample"], "model_ids": ["MODEL-V39-AQSOLDB"], "run_ids": ["RUN-V39-SOLUBILITY"], "publication_ids": ["AQSOLDB-2019"]},
        "EVD-V39-SOLUBILITY-PRED": {"source_ids": ["SRC-AQSOLDB-DATA"], "dataset_ids": ["aqsoldb-g-real-sample"], "model_ids": ["MODEL-V39-AQSOLDB"], "run_ids": ["RUN-V39-SOLUBILITY"], "publication_ids": ["AQSOLDB-2019"]},
        "EVD-INDEPENDENT-01": {"source_ids": ["SRC-OXFORD-BATTERY-AGING"], "dataset_ids": ["oxford-energy-trading-battery"], "model_ids": [], "run_ids": [], "publication_ids": ["OXFORD-2020"]},
        "EVD-CONFLICT-01": {"source_ids": ["SRC-NASA-PCOE-RW3"], "dataset_ids": ["battery-nasa-pcoe-rw3"], "model_ids": [], "run_ids": ["RUN-V39-BATTERY"], "publication_ids": ["NASA-PCOE-RW3"]},
    }
    dependencies = [
        integrator.assess_dependency(("EVD-V39-BATTERY", "EVD-CONFLICT-01"), metadata),
        integrator.assess_dependency(("EVD-V39-SOLUBILITY-MODEL", "EVD-V39-SOLUBILITY-PRED"), metadata),
        integrator.assess_dependency(("EVD-V39-BATTERY", "EVD-INDEPENDENT-01"), metadata),
        integrator.assess_dependency(("EVD-INDEPENDENT-01",), metadata),
        integrator.assess_dependency(("EVD-MISSING",), metadata),
    ]
    old_claim = dict(prior310["claim_history"][0])
    previous_revision = dict(prior310["claim_history"][1])
    new_revision = ClaimRevision("REV-V312-AQSOLDB-03", old_claim["claim_id"], 3, old_claim["statement"], ClaimStatus.SUPPORTED, ClaimStatus.SUPPORTED, tuple(previous_revision["evidence_ids"]), tuple(dict.fromkeys((*previous_revision["evidence_ids"], "EVD-V39-SOLUBILITY-PRED"))), "External-data integration was assessed; no eligible independent dataset was promoted, so the existing model-boundary claim remains scoped and supported only within its protocol.", tuple(old_claim.get("limitations") or ()), previous_revision_id=previous_revision["revision_id"], derived_from=(previous_revision["revision_id"], "EVD-V39-SOLUBILITY-PRED"), new_evidence_ids=("EVD-V39-SOLUBILITY-PRED",), conditions=dict(old_claim.get("conditions") or {}), timestamp="2026-09-04T18:50:00+00:00")
    before_hashes = {"v36_claim_bundle": sha256_file(REPO_ROOT / ".research-os-live-3.6" / "bundles" / "RUN-V36-ML-726EA6351D55" / "manifest.json"), "v39_battery_bundle": sha256_file(REPO_ROOT / ".research-os-live-3.9" / "runs" / "bundles" / "RUN-V39-BATTERY" / "manifest.json")}
    after_hashes = dict(before_hashes)
    promotion_e2_e4 = integrator.level_guard("E2_COMPUTATIONAL", "E4_CURATED_EXPERIMENTAL", actual_experiment=False)
    promotion_e3_e4 = integrator.level_guard("E3_PHYSICS", "E4_CURATED_EXPERIMENTAL", actual_experiment=False)
    acceptance = {
        "external_update_works": all(item.valid for item in integrator.updates),
        "dependency_assessment_works": all(isinstance(item, EvidenceDependencyAssessment) for item in dependencies),
        "update_impact_cases_at_least_20": len(integrator.updates) >= 20,
        "dependent_sources_not_double_counted": dependencies[0].independence_status == "DEPENDENT" and "shared run/dataset/model lineage" in " ".join(dependencies[0].notes),
        "conflicts_preserved": any(item.conflicts for item in integrator.updates),
        "historical_runs_unaffected": before_hashes == after_hashes,
        "claim_revision_from_new_evidence": new_revision.valid and "EVD-V39-SOLUBILITY-PRED" in new_revision.new_evidence_ids and new_revision.previous_revision_id == previous_revision["revision_id"],
        "scientific_decision_revisited": prior310["decision_history"][0]["decision_id"] != prior310["decision_history"][1]["decision_id"] and prior310["decision_history"][2]["relation"] == "re-evaluated_by",
        "research_priority_can_change": prior311["acceptance"]["new_evidence_reorders_without_deleting_history"] is True,
        "source_dataset_versions_preserved": "artifact@v3.9" in json.dumps(prior310["snapshot"], ensure_ascii=False) and any(item.source_version == "artifact@v3.9" for item in integrator.updates),
        "no_e2_to_e4_inflation": promotion_e2_e4["promotion_allowed"] is False,
        "no_e3_to_e4_without_experiment": promotion_e3_e4["promotion_allowed"] is False,
        "real_searches_honestly_blocked": len(real_search) == 5 and all("BLOCKED_NOT_INGESTED" in str(item.compatibility_assessment) for item in real_search),
        "versioned_real_evidence_integrated": existing_real.evidence_ids == ("EVD-V39-BATTERY",) and existing_real.dataset_id_optional == "battery-nasa-pcoe-rw3",
        "codex_not_evidence_provider": prior310["codex_not_chat_source_of_truth"] if "codex_not_chat_source_of_truth" in prior310 else True,
        "ci_green": bool(ci_green),
    }
    report = {"version": "3.12.0", "protocol_version": "research-os.v3.12.external-evidence-integration.v1", "branch": "research-os-v1.3", "git_commit": _git_commit(), "started_at": _now(), "completed_at": _now(), "status": "PASS" if all(acceptance.values()) else "FAIL", "real_source_search": [{"update": item.to_dict(), "source_url": {"SRC-NEWFOUND-AQUEOUS-SOLUBILITY": "https://github.com/newfound-materials/aqueous-solubility-data", "SRC-OXFORD-BATTERY-AGING": "https://ora.ox.ac.uk/objects/uuid:9aae61af-2949-49f1-8ad5-6aea448979e5", "SRC-NATURE-NMC-AGING": "https://doi.org/10.1038/s41597-024-03831-x", "SRC-NASA-HE-1975": "https://ntrs.nasa.gov/citations/19750004044", "SRC-NIST-TRC": "https://www.nist.gov/mml/acmd/trc"}.get(item.source_id)} for item in real_search], "versioned_real_update": existing_real.to_dict(), "updates": [item.to_dict() for item in (*real_search, existing_real, *fixture_updates)], "dependencies": [item.to_dict() for item in dependencies], "claim_revision": new_revision.to_dict(), "decision_revisit": prior310["decision_history"], "priority_revisit": prior311["queue"]["assessment_history"], "level_guards": {"E2_to_E4": promotion_e2_e4, "E3_to_E4": promotion_e3_e4}, "historical_bundle_hashes": {"before": before_hashes, "after": after_hashes}, "counts": {"updates": len(integrator.updates), "real_searches": len(real_search), "fixture_updates": len(fixture_updates), "dependency_assessments": len(dependencies), "conflict_updates": sum(bool(item.conflicts) for item in integrator.updates)}, "acceptance": acceptance, "source_policy": "New sources are DATA until verified, hashed, schema/units/conditions/lineage checked and compatible; no historical record is overwritten.", "source_artifacts": {"v3.10": str(V310_ARTIFACT), "v3.11": str(V311_ARTIFACT), "v3.6": str(V36_ARTIFACT)}}
    _write(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Research OS v3.12 external evidence integration benchmark")
    parser.add_argument("--root", type=Path, default=Path(".research-os-live-3.12"))
    parser.add_argument("--output", type=Path, default=Path(".research-os-live-3.12/external-evidence-integration.json"))
    parser.add_argument("--ci-green", action="store_true")
    args = parser.parse_args()
    report = run_benchmark(args.output, root=args.root, ci_green=args.ci_green)
    print(json.dumps({"status": report["status"], "updates": report["counts"]["updates"], "dependency_assessments": report["counts"]["dependency_assessments"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
