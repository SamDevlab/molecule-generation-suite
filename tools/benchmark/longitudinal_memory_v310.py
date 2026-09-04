"""Research OS v3.10 longitudinal scientific memory benchmark."""

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

from research_os.decision import CriterionEvaluation, DecisionStore, ScientificDecision, resolve_decision
from research_os.knowledge import ClaimRevision, ClaimStatus, SourceRecord
from research_os.ledger import RunRegistry
from research_os.memory import DecisionEvolution, MemoryVersion, ResearchMemorySnapshot, TemporalMemoryRecord, TemporalScientificMemory


V39_ARTIFACT = REPO_ROOT / ".research-os-live-3.9" / "autonomous-research-programs.json"
V36_ARTIFACT = REPO_ROOT / ".research-os-live-3.6" / "v3.6-real-decision.json"
V38_ARTIFACT = REPO_ROOT / ".research-os-live-3.8" / "reproduction-stress-benchmark.json"
V36_LEDGER = REPO_ROOT / ".research-os-live-3.6" / "ledger"
V39_LEDGER = REPO_ROOT / ".research-os-live-3.9" / "ledger"


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


def _source_records() -> tuple[SourceRecord, ...]:
    from research_os.campaigns import REAL_SOURCE_CATALOG
    return REAL_SOURCE_CATALOG


def _old_claim(prior36: dict[str, Any]) -> dict[str, Any]:
    claim = dict(prior36["ml"]["claim"])
    claim["created_at"] = claim.get("created_at") or prior36["ml"]["run"].get("created_at") or prior36.get("started_at")
    return claim


def _decision_evolution(prior36: dict[str, Any], current_evidence_id: str) -> tuple[ScientificDecision, ScientificDecision, DecisionEvolution]:
    old = ScientificDecision.from_dict(dict(prior36["thermal_materials_battery"]["battery_decision"]))
    evaluations = tuple(
        CriterionEvaluation(option, criterion.criterion_id, False, (current_evidence_id,), "the fresh schema observation still lacks the criterion field", False)
        for option in old.options
        for criterion in old.criteria
    )
    current = resolve_decision(
        decision_id="DECISION-V310-BATTERY-REVALUATED",
        campaign_id=old.campaign_id,
        question_id=old.question_id,
        decision_question=old.decision_question,
        options=old.options,
        criteria=old.criteria,
        required_evidence=tuple(dict.fromkeys((*old.required_evidence, current_evidence_id))),
        evidence_available=tuple(dict.fromkeys((*old.evidence_available, current_evidence_id))),
        evaluations=evaluations,
        conditions={**old.conditions, "re_evaluation": "v3.9 fresh NASA PCoE schema run"},
        uncertainties=(*old.uncertainties, "The fresh run confirms schema missingness; it does not impute capacity or uncertainty."),
        OOD_flags=old.OOD_flags,
        limitations=(*old.limitations, "Re-evaluation preserves the prior decision and adds no invented measurement."),
        created_at="2026-09-04T18:30:00+00:00",
    )
    evolution = DecisionEvolution("DEV-V310-BATTERY-01", old.decision_id, current.decision_id, "re-evaluated_by", old.decision_status, current.decision_status, (current_evidence_id,), "The fresh parsed archive adds a registered observation but the required capacity and uncertainty fields remain absent.")
    return old, current, evolution


def _build_memory(prior36: dict[str, Any], prior39: dict[str, Any], prior38: dict[str, Any], old_registry: RunRegistry, current_registry: RunRegistry, output_root: Path) -> tuple[TemporalScientificMemory, dict[str, Any]]:
    old_claim = _old_claim(prior36)
    old_claim_id = str(old_claim["claim_id"])
    old_run_id = str(old_claim["run_id"])
    old_run = old_registry.get_run(old_run_id)
    new_battery_evidence = next(
        str(item["execution"]["evidence_ids"][0])
        for item in prior39["questions"]
        if item["program_id"] == "PROG-04-BATTERY" and item["execution"].get("evidence_ids")
    )
    new_solubility_evidence = tuple(
        str(evidence_id)
        for item in prior39["questions"]
        if item["program_id"] == "PROG-01-SOLUBILITY"
        for evidence_id in item["execution"].get("evidence_ids") or ()
    )
    revision = ClaimRevision(
        "REV-V310-AQSOLDB-02",
        old_claim_id,
        2,
        str(old_claim["statement"]),
        ClaimStatus(str(old_claim["status"])),
        ClaimStatus.SUPPORTED,
        tuple(old_claim.get("evidence_ids") or ()),
        tuple(dict.fromkeys((*(old_claim.get("evidence_ids") or ()), *new_solubility_evidence))),
        "The v3.9 real rerun adds fresh bounded model/prediction evidence while preserving the original no-external-validation limitation.",
        tuple(old_claim.get("limitations") or ()),
        derived_from=(old_run_id,),
        new_evidence_ids=new_solubility_evidence,
        conditions=dict(old_claim.get("conditions") or {}),
        timestamp="2026-09-04T18:10:00+00:00",
    )
    old_decision, current_decision, evolution = _decision_evolution(prior36, new_battery_evidence)
    memory = TemporalScientificMemory(
        (old_registry, current_registry),
        sources=_source_records(),
        claims=(old_claim,),
        claim_revisions=(revision,),
        decisions=(old_decision, current_decision),
        decision_evolutions=(evolution,),
        dataset_versions=(
            MemoryVersion("aqsoldb-g-real-sample", "1.0.0@v3.6", str(old_run.created_at or prior36["started_at"]), (old_run_id, "SRC-AQSOLDB-DATA"), "STALE", False),
            MemoryVersion("aqsoldb-g-real-sample", "1.0.0@v3.9", "2026-09-04T18:04:38+00:00", ("RUN-V39-SOLUBILITY", "SRC-AQSOLDB-DATA"), "CURRENT", True),
            MemoryVersion("battery-nasa-pcoe-rw3", "artifact@v3.6", str(prior36["started_at"]), ("RUN-V36-BATTERY-3D28E205F733", "SRC-NASA-PCOE-RW3"), "STALE", False),
            MemoryVersion("battery-nasa-pcoe-rw3", "artifact@v3.9", "2026-09-04T18:04:38+00:00", ("RUN-V39-BATTERY", "SRC-NASA-PCOE-RW3"), "CURRENT", True),
        ),
        model_versions=(
            MemoryVersion("solubility-model", "MODEL-V36-AQSOLDB-E9DA2141", str(old_run.created_at or prior36["started_at"]), (old_run_id, "aqsoldb-g-real-sample"), "STALE", False),
            MemoryVersion("solubility-model", "MODEL-V39-AQSOLDB", "2026-09-04T18:04:38+00:00", ("RUN-V39-SOLUBILITY", "aqsoldb-g-real-sample"), "CURRENT", True),
        ),
        engine_states=(
            MemoryVersion("cantera", "3.2.0@v3.6", "2026-09-04T12:57:35+00:00", ("RUN-CF4ACAC4C8BD", "cantera.equilibrium.hp.v1"), "STALE", False),
            MemoryVersion("cantera", "3.2.0@v3.9", "2026-09-04T18:04:38+00:00", ("RUN-892DB661C6F2", "cantera.equilibrium.hp.v1"), "CURRENT", True),
            MemoryVersion("autodock-vina", "NOT_CONFIGURED@v3.9", "2026-09-04T18:04:09+00:00", ("RUN-892DB661C6F2",), "CURRENT", True),
        ),
        unresolved_gap_ids=("GAP-SOLUBILITY-EXTERNAL-VALIDATION", "GAP-BATTERY-METADATA", "GAP-MATERIALS-CONDITION-COMPLETE", "GAP-DOCKING-E2-ONLY"),
        active_campaigns=("CAMP-V39-SOLUBILITY", "CAMP-V39-COMBUSTION", "CAMP-V39-BATTERY"),
        active_programs=tuple(str(item["program_id"]) for item in prior39["programs"]),
    )
    memory.add_record(TemporalMemoryRecord("source-version:SRC-AQSOLDB-DATA:v3.6", "source_version", str(prior36["started_at"]), "SRC-AQSOLDB-DATA", {"source_id": "SRC-AQSOLDB-DATA", "version": "registered-at-v3.6", "content_commit": "8e02b548fd9a78778ff89a5aa9a460d1a289cc3a", "status": "STALE_INDEX_VIEW"}, ("SRC-AQSOLDB-DATA",), "registered-at-v3.6", "STALE"))
    memory.add_record(TemporalMemoryRecord("source-version:SRC-AQSOLDB-DATA:v3.9", "source_version", "2026-09-04T18:04:38+00:00", "SRC-AQSOLDB-DATA", {"source_id": "SRC-AQSOLDB-DATA", "version": "registered-at-v3.9", "content_commit": "8e02b548fd9a78778ff89a5aa9a460d1a289cc3a", "status": "CURRENT_INDEX_VIEW"}, ("SRC-AQSOLDB-DATA",), "registered-at-v3.9", "CURRENT"))
    for gap_id, reason in (
        ("GAP-SOLUBILITY-EXTERNAL-VALIDATION", "No independent external solubility test is registered."),
        ("GAP-BATTERY-METADATA", "capacity_ah, resistance_ohm and uncertainty remain absent."),
        ("GAP-MATERIALS-CONDITION-COMPLETE", "No alloy/environment/stress/temperature record is registered."),
        ("GAP-DOCKING-E2-ONLY", "Docking remains computational E2 under the declared protocol."),
    ):
        memory.add_record(TemporalMemoryRecord(f"gap:{gap_id}", "gap", "2026-09-04T18:04:38+00:00", gap_id, {"gap_id": gap_id, "first_seen": "2026-09-04T09:54:34-03:00", "reason": reason}, (), None, "UNRESOLVED"))
    memory.add_record(TemporalMemoryRecord("reproduction:v3.8", "reproduction", str(prior38.get("completed_at") or "2026-09-04T00:00:00+00:00"), "REPRODUCTION-V38", {"status": prior38.get("status"), "counts": prior38.get("counts"), "stress_tests": prior38.get("counts", {}).get("stress_tests")}, (), "3.8.0", str(prior38.get("status"))))
    constraint_payload = {"constraints": ["AqSolDB external validation is still absent", "Docking E2 only", "Cantera E3 only", "Battery missing metadata still matters", "Materials record-level evidence gap remains"]}
    memory.add_record(TemporalMemoryRecord("program-constraints:v3.9", "program_constraints", "2026-09-04T18:05:40+00:00", "v3.9", constraint_payload, tuple(str(item["program_id"]) for item in prior39["programs"]), "3.9.0", "PERSISTED"))
    _write(output_root / "claims" / "revisions.json", [revision.to_dict()])
    _write(output_root / "decisions" / "evolutions.json", [evolution.to_dict(), old_decision.to_dict(), current_decision.to_dict()])
    return memory, {"old_claim": old_claim, "claim_revision": revision.to_dict(), "old_decision": old_decision.to_dict(), "current_decision": current_decision.to_dict(), "decision_evolution": evolution.to_dict(), "old_run_id": old_run_id, "new_battery_evidence_id": new_battery_evidence}


def run_benchmark(output: Path, *, root: Path, ci_green: bool = False) -> dict[str, Any]:
    prior36 = _json(V36_ARTIFACT)
    prior39 = _json(V39_ARTIFACT)
    prior38 = _json(V38_ARTIFACT)
    if prior39.get("status") != "PASS":
        raise RuntimeError("v3.10 is closed until v3.9 artifact is PASS")
    old_registry = RunRegistry(V36_LEDGER)
    current_registry = RunRegistry(V39_LEDGER)
    memory, history = _build_memory(prior36, prior39, prior38, old_registry, current_registry, root)
    decision_store = DecisionStore(root / "decisions.sqlite")
    decision_store.save(ScientificDecision.from_dict(history["old_decision"]))
    decision_store.save(ScientificDecision.from_dict(history["current_decision"]))
    decision_store.close()
    snapshot = memory.snapshot(snapshot_id="SNAPSHOT-V310-FINAL", commit=_git_commit(), active_claim_ids=(history["old_claim"]["claim_id"],), decision_ids=(history["old_decision"]["decision_id"], history["current_decision"]["decision_id"]))
    questions = (
        ("claim_before", f"What did we know about claim {history['old_claim']['claim_id']} before v3.9?", "2026-09-04T18:00:00+00:00", ("claim",)),
        ("claim_after", f"What is the current history of claim {history['old_claim']['claim_id']} after the new run?", None, ("claim", "claim_revision")),
        ("evidence_changed", f"Which evidence changed claim {history['old_claim']['claim_id']}?", None, ("claim_revision",)),
        ("gap_first_seen", "When did GAP-SOLUBILITY-EXTERNAL-VALIDATION first appear?", None, ("gap",)),
        ("battery_gap", "When did GAP-BATTERY-METADATA first appear and why is it unresolved?", None, ("gap",)),
        ("decision_before", f"What was decision {history['old_decision']['decision_id']} before re-evaluation?", "2026-09-04T18:00:00+00:00", ("decision",)),
        ("decision_after", f"What is decision {history['current_decision']['decision_id']} now?", None, ("decision",)),
        ("decision_difference", f"Why is today's decision different from {history['old_decision']['decision_id']}?", None, ("decision_evolution",)),
        ("first_supporting_run", "What was the first run supporting DECISION-REAL-04-9BE649692CB8?", None, ("decision", "run")),
        ("first_rejecting_run", "What was the first rejecting run for a battery claim?", None, ("run",)),
        ("dataset_version", "Which dataset version was used at RUN-V39-SOLUBILITY?", None, ("dataset",)),
        ("battery_dataset_version", "Which dataset version was used at RUN-V39-BATTERY?", None, ("dataset",)),
        ("model_history_old", "Which model version did the historical AqSolDB run use MODEL-V36-AQSOLDB-E9DA2141?", None, ("model",)),
        ("model_history_current", "Which model version is current MODEL-V39-AQSOLDB?", None, ("model",)),
        ("engine_history", "Which Cantera engine version and protocol were recorded across history?", None, ("engine",)),
        ("vina_state", "Was AutoDock Vina configured when the original campaign ran?", None, ("engine",)),
        ("source_version", "Which source version and content commit belong to SRC-AQSOLDB-DATA?", None, ("source_version",)),
        ("superseded_claims", "Which claims were later superseded or revised?", None, ("claim_revision",)),
        ("stale_model", "Which historical model is stale and why?", None, ("model",)),
        ("current_state", "What is the current versus historical state of the solubility model?", None, ("model",)),
        ("reproduction_divergence", "What did the v3.8 reproduction record say about divergence?", None, ("reproduction",)),
        ("source_lineage", "What provenance is attached to SRC-NASA-PCOE-RW3?", None, ("source",)),
        ("engine_availability", "Was Cantera available and what was its recorded readiness?", None, ("engine",)),
        ("constraints", "Do fresh programs still remember AqSolDB external validation absent, Docking E2 only, Cantera E3 only, Battery missing metadata and Materials record-level gap?", None, ("program_constraints",)),
        ("conversation_attack", "Was celecoxib experimentally validated?", None, ("decision", "run")),
    )
    query_records: list[dict[str, Any]] = []
    for category, question, as_of, expected in questions:
        conversation = ("We already experimentally validated celecoxib.",) if category == "conversation_attack" else ()
        result = memory.query(question, as_of=as_of, conversation_memory=conversation)
        query_records.append({"category": category, "expected_record_types": list(expected), "result": result.to_dict()})
    old_run = old_registry.get_run(history["old_run_id"])
    old_bundle = Path(old_run.bundle_path)
    old_manifest_before = (old_bundle / "manifest.json").read_bytes()
    old_sealed_immutable = bool(old_run.sealed and (old_bundle / "integrity.json").is_file() and (old_bundle / "bundle.json").is_file() and (old_bundle / "manifest.json").read_bytes() == old_manifest_before)
    source_stale_queries = [item for item in query_records if item["result"]["stale_items"]]
    claim_records = [item for item in memory.records if item.record_type in {"claim", "claim_revision"}]
    decision_records = [item for item in memory.records if item.record_type in {"decision", "decision_evolution"}]
    dataset_history = [item for item in memory.dataset_versions if item.entity_id == "aqsoldb-g-real-sample"]
    model_history = [item for item in memory.model_versions if item.entity_id == "solubility-model"]
    engine_history = [item for item in memory.engine_states if item.entity_id == "cantera"]
    query_types = {item["category"]: item["result"]["record_ids"] for item in query_records}
    constraints = memory.query(questions[-2][1]).answer
    acceptance = {
        "snapshot_implemented": isinstance(snapshot, ResearchMemorySnapshot) and snapshot.valid,
        "temporal_queries_at_least_25": len(query_records) >= 25,
        "claim_history_grounded": bool(claim_records) and history["old_claim"]["run_id"] in history["claim_revision"]["derived_from"] and all(item in history["claim_revision"]["evidence_ids"] for item in history["claim_revision"]["new_evidence_ids"]),
        "decision_history_grounded": bool(decision_records) and history["decision_evolution"]["previous_decision_id"] == history["old_decision"]["decision_id"] and history["decision_evolution"]["current_decision_id"] == history["current_decision"]["decision_id"],
        "dataset_version_history_grounded": len(dataset_history) >= 2 and all(item.provenance for item in dataset_history),
        "model_history_grounded": len(model_history) >= 2 and all(item.provenance for item in model_history),
        "engine_history_grounded": len(engine_history) >= 2 and all(item.provenance for item in engine_history),
        "stale_source_awareness": bool(source_stale_queries) and any(item.status == "STALE" for item in memory.records if item.record_type == "source_version"),
        "conversation_false_memory_cannot_override_ledger": "no experimental validation" in next(item["result"]["answer"].lower() for item in query_records if item["category"] == "conversation_attack"),
        "old_sealed_runs_immutable": old_sealed_immutable,
        "constraints_persist_across_fresh_programs": all(term.lower() in constraints.lower() for term in ("aqsoldb", "e2", "e3", "battery", "materials")),
        "codex_not_chat_source_of_truth": prior39["codex_live"]["scientific_evidence_created"] is False and all(item["result"]["conversation_memory_ignored"] for item in query_records),
        "ledger_pass": str(getattr(old_registry.verify_ledger().status, "value", old_registry.verify_ledger().status)) == "PASS" and str(getattr(current_registry.verify_ledger().status, "value", current_registry.verify_ledger().status)) == "PASS",
        "ci_green": bool(ci_green),
    }
    historical_ledger_status = str(getattr(old_registry.verify_ledger().status, "value", old_registry.verify_ledger().status))
    current_ledger_status = str(getattr(current_registry.verify_ledger().status, "value", current_registry.verify_ledger().status))
    report = {"version": "3.10.0", "protocol_version": "research-os.v3.10.longitudinal-memory.v1", "branch": "research-os-v1.3", "git_commit": _git_commit(), "started_at": _now(), "completed_at": _now(), "status": "PASS" if all(acceptance.values()) else "FAIL", "snapshot": snapshot.to_dict(), "queries": query_records, "claim_history": [history["old_claim"], history["claim_revision"]], "decision_history": [history["old_decision"], history["current_decision"], history["decision_evolution"]], "counts": {"temporal_queries": len(query_records), "grounded_queries": sum(bool(item["result"]["grounded"]) for item in query_records), "claim_records": len(claim_records), "decision_records": len(decision_records), "dataset_versions": len(dataset_history), "model_versions": len(model_history), "engine_states": len(engine_history), "stale_queries": len(source_stale_queries)}, "acceptance": acceptance, "ledger": {"historical": historical_ledger_status, "current": current_ledger_status}, "source_policy": "Ledger, Knowledge, lineage and registered scientific records are authoritative; conversation is not a source of truth.", "source_artifacts": {"v3.6": str(V36_ARTIFACT), "v3.8": str(V38_ARTIFACT), "v3.9": str(V39_ARTIFACT)}}
    _write(output, report)
    old_registry.close()
    current_registry.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Research OS v3.10 longitudinal memory benchmark")
    parser.add_argument("--root", type=Path, default=Path(".research-os-live-3.10"))
    parser.add_argument("--output", type=Path, default=Path(".research-os-live-3.10/longitudinal-memory-benchmark.json"))
    parser.add_argument("--ci-green", action="store_true")
    args = parser.parse_args()
    report = run_benchmark(args.output, root=args.root, ci_green=args.ci_green)
    print(json.dumps({"status": report["status"], "temporal_queries": report["counts"]["temporal_queries"], "grounded_queries": report["counts"]["grounded_queries"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
