"""MOLDISC-019: first Biolab experimental bridge and autonomous-loop transition.

MOLDISC-019 closes the current computation-only frontier.  It freezes a
vendor-neutral physical panel, validates future external results without
fabricating evidence, and records the first bounded next-action decision.
No docking, molecule generation, lead selection, or evidence promotion is
performed by this module unless a caller supplies a separately valid result.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from research_os.core.hashing import sha256_file, sha256_json
from research_os.external_evidence import ExternalEvidenceIntegrator, ExternalEvidenceUpdate
from research_os.molecular_discovery.biolab_loop import (
    BiolabScientificState,
    apply_e4_feedback,
    default_moldisc018_state,
    evaluate_next_action,
)


PROGRAM_ID = "MOLDISC-019"
PROGRAM_VERSION = "1.0"
PARENT_MOLDISC018_HASH = "7b900a85ef70b13120107ab7dca7e5c21da34053942b48379c4c4f51e418086a"
PARENT_MOLDISC018_PROTOCOL_HASH = "403907a0a9e911a313bfaf27d01b75d8b11d84dc742eac40caf9c7dc020cbb66"
PANEL_ID = "BIOEXP-001-SOLUBILITY-2X2"
PACKAGE_RELATIVE_PATH = "experimental_packages/biolab-physical-loop-0"
BIOEXP001_ID = "BIOEXP-001-SOLUBILITY-2X2"
BIOEXP002_ID = "BIOEXP-002-PROTEASE-2X2"
REQUIRED_RESULT_FIELDS = (
    "experiment_id",
    "protocol_id",
    "experiment_family",
    "laboratory",
    "laboratory_report_id",
    "performed_date",
    "compound_id",
    "panel_key",
    "batch_id",
    "sample_purity",
    "sample_identity_method",
    "measurement_name",
    "measurement_value",
    "measurement_units",
    "replicate_values",
    "conditions",
    "controls",
    "raw_artifacts",
    "raw_artifact_hashes",
    "report_file",
    "report_hash",
    "provider",
    "provenance",
    "notes",
)
PROCUREMENT_STATUSES = (
    "UNKNOWN",
    "COMMERCIAL_SOURCE_FOUND",
    "QUOTE_REQUESTED",
    "CUSTOM_SYNTHESIS_REQUIRED",
    "SAMPLE_AVAILABLE",
    "UNAVAILABLE",
)
PHYSICAL_LOOP_STATES = (
    "COMPUTATIONAL_PHASE_COMPLETE",
    "EXPERIMENT_PACKET_PREPARED",
    "AWAITING_EXTERNAL_PROTOCOL",
    "AWAITING_SAMPLE",
    "AWAITING_EXPERIMENT",
    "EXPERIMENT_RESULT_RECEIVED",
    "RESULT_VALIDATION_FAILED",
    "E4_RESULT_INGESTED",
    "E5_RESULT_INGESTED",
)


class MOLDISC019Error(RuntimeError):
    """Fail-closed MOLDISC-019 contract or result validation error."""


def _load_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MOLDISC019Error(f"could not load JSON: {path}") from exc
    if not isinstance(value, dict):
        raise MOLDISC019Error(f"JSON object required: {path}")
    return value


def _write_json(path: str | Path, value: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _as_nonempty(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {} and value != ()


def protocol_hash(config: Mapping[str, Any]) -> str:
    """Hash only the declared operational protocol, excluding its identity fields."""

    return sha256_json(config.get("protocol", {}))


def scientific_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return the immutable MOLDISC-019 scientific identity payload."""

    payload = config.get("scientific_identity")
    if not isinstance(payload, Mapping):
        raise MOLDISC019Error("scientific_identity is required")
    return json.loads(json.dumps(payload, sort_keys=True))


def program_scientific_hash(config: Mapping[str, Any]) -> str:
    return sha256_json(scientific_payload(config))


def _expected_panel() -> dict[str, dict[str, Any]]:
    return {
        "A0B0": {
            "candidate_id": "MOLDISC-011-JE2-286E6F2BE8",
            "variant_id": "A0B0-CONTROL",
            "factor_a": "CONTROL",
            "factor_b": "CONTROL",
            "canonical_isomeric_smiles": "CC1(C)SCN(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2)[C@@H]1C(=O)NCc1ccccc1",
            "inchikey": "DRIAWXDDGSORDT-KKUQBAQOSA-N",
            "formula": "C30H33N3O5S",
            "heavy_atom_count": 39,
        },
        "A1B0": {
            "candidate_id": "MOLDISC-014-SOURCE-DELTA-OH",
            "variant_id": "A1B0-DELTA-OH",
            "factor_a": "DELTA-OH",
            "factor_b": "CONTROL",
            "canonical_isomeric_smiles": "CC1(C)SCN(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2ccccc2)[C@@H]1C(=O)NCc1ccccc1",
            "inchikey": "NAZMDUVPQSKJEQ-KKUQBAQOSA-N",
            "formula": "C30H33N3O4S",
            "heavy_atom_count": 38,
        },
        "A0B1": {
            "candidate_id": "MOLDISC-014-SOURCE-DELTA-NSUB",
            "variant_id": "A0B1-DELTA-NSUB",
            "factor_a": "CONTROL",
            "factor_b": "DELTA-NSUB",
            "canonical_isomeric_smiles": "CC(C)(C)NC(=O)[C@H]1N(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2cccc(O)c2)CSC1(C)C",
            "inchikey": "DMSDTDPQGPRTNA-FDFHNCONSA-N",
            "formula": "C27H35N3O5S",
            "heavy_atom_count": 36,
        },
        "A1B1": {
            "candidate_id": "MOLDISC-014-SOURCE-DELTA-BOTH",
            "variant_id": "A1B1-DELTA-BOTH",
            "factor_a": "DELTA-OH",
            "factor_b": "DELTA-NSUB",
            "canonical_isomeric_smiles": "CC(C)(C)NC(=O)[C@H]1N(C(=O)[C@@H](O)[C@H](Cc2ccccc2)NC(=O)c2ccccc2)CSC1(C)C",
            "inchikey": "URHJIBSBOJFXDI-FDFHNCONSA-N",
            "formula": "C27H35N3O4S",
            "heavy_atom_count": 35,
        },
    }


def load_program_config_v19(path: str | Path) -> dict[str, Any]:
    config = _load_json(path)
    if config.get("program_id") != PROGRAM_ID or config.get("program_version") != PROGRAM_VERSION:
        raise MOLDISC019Error("MOLDISC-019 program identity/version drifted")
    parent = config.get("parents", {}).get("moldisc018", {})
    if parent.get("program_scientific_hash") != PARENT_MOLDISC018_HASH or parent.get("protocol_hash") != PARENT_MOLDISC018_PROTOCOL_HASH:
        raise MOLDISC019Error("MOLDISC-018 parent identity drifted")
    if config.get("phase_transition", {}).get("before") != "COMPUTATIONAL_MOLECULAR_DISCOVERY" or config.get("phase_transition", {}).get("after") != "BIOLAB_EXPERIMENTAL_FEEDBACK":
        raise MOLDISC019Error("phase transition drifted")
    panel = config.get("panel", {})
    if panel.get("panel_id") != PANEL_ID or panel.get("member_count") != 4:
        raise MOLDISC019Error("BIOEXP-001 panel identity drifted")
    members = panel.get("members", {})
    expected = _expected_panel()
    if set(members) != set(expected):
        raise MOLDISC019Error("panel member set drifted")
    for panel_key, identity in expected.items():
        member = members.get(panel_key, {})
        for field in ("candidate_id", "variant_id", "factor_a", "factor_b", "canonical_isomeric_smiles", "inchikey", "formula", "heavy_atom_count"):
            if member.get(field) != identity[field]:
                raise MOLDISC019Error(f"panel identity drifted: {panel_key}/{field}")
    gates = config.get("gates", {})
    if gates.get("same_level_continuation_allowed") is not False or gates.get("next_generation_allowed") is not False:
        raise MOLDISC019Error("MOLDISC-019 gates must default closed")
    if config.get("boundaries", {}).get("new_docking_runs") != 0 or config.get("boundaries", {}).get("molecule_generation_executed") is not False:
        raise MOLDISC019Error("MOLDISC-019 computation boundary drifted")
    return config


def _package_files(package_root: Path) -> tuple[Path, ...]:
    return tuple(sorted(path for path in package_root.rglob("*") if path.is_file()))


def package_identity(package_root: str | Path) -> dict[str, Any]:
    root = Path(package_root)
    if not root.is_dir():
        raise MOLDISC019Error(f"experimental package not found: {root}")
    files = _package_files(root)
    if not files:
        raise MOLDISC019Error("experimental package is empty")
    file_hashes = {str(path.relative_to(root)).replace("\\", "/"): sha256_file(path) for path in files}
    return {"package_id": "BIOLAB_PHYSICAL_LOOP_0", "root": str(root), "file_hashes": file_hashes, "package_hash": sha256_json(file_hashes)}


def prepare_package(config_path: str | Path, package_root: str | Path) -> dict[str, Any]:
    config = load_program_config_v19(config_path)
    package = package_identity(package_root)
    panel = _load_json(Path(package_root) / "panel_manifest.json")
    if panel.get("panel_id") != PANEL_ID or len(panel.get("members", [])) != 4:
        raise MOLDISC019Error("prepared package does not contain the frozen four-member panel")
    return {
        "program_id": PROGRAM_ID,
        "program_protocol_hash": protocol_hash(config),
        "program_scientific_hash": program_scientific_hash(config),
        "package": package,
        "physical_loop_state": "EXPERIMENT_PACKET_PREPARED",
        "status": "AWAITING_EXTERNAL_PROTOCOL_OR_QUOTE",
        "real_experiment_executed": False,
        "e4_created": False,
        "e5_created": False,
    }


def package_status(package_root: str | Path) -> dict[str, Any]:
    root = Path(package_root)
    package = package_identity(root)
    request = _load_json(root / "BIOEXP-001" / "experiment_request.json")
    missing = _load_json(root / "BIOEXP-001" / "missing_protocol_fields.json")
    status = "AWAITING_EXTERNAL_PROTOCOL_OR_QUOTE" if missing.get("missing_fields") else "EXPERIMENT_PACKET_READY"
    return {
        "package_id": "BIOLAB_PHYSICAL_LOOP_0",
        "physical_loop_state": "AWAITING_EXTERNAL_PROTOCOL" if status.startswith("AWAITING") else "EXPERIMENT_PACKET_PREPARED",
        "status": status,
        "experiment_id": request.get("experiment_id"),
        "missing_protocol_fields": list(missing.get("missing_fields", [])),
        "real_experiment_executed": False,
        "e4_created": False,
        "e5_created": False,
        "package_hash": package["package_hash"],
    }


def build_first_decision(state: BiolabScientificState | None = None) -> dict[str, Any]:
    current = state or default_moldisc018_state()
    snapshot = evaluate_next_action(current)
    decision = snapshot.decision
    def stable(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: stable(item) for key, item in value.items() if key not in {"created_at", "digest"}}
        if isinstance(value, list):
            return [stable(item) for item in value]
        return value

    result = {
        "schema_version": "research-os.molecular-discovery.biolab-loop.v0.1",
        "current_program": current.current_program,
        "current_max_local_evidence": current.highest_local_evidence,
        "target_gap": decision.target_gap,
        "required_evidence": decision.required_evidence,
        "selected_action": decision.selected_action,
        "computational_continuation_allowed": decision.computational_continuation_allowed,
        "stop_reason": decision.stop_reason,
        "status": decision.status,
        "next_generation_allowed": decision.next_generation_allowed,
        "blocked_actions": list(decision.blocked_actions),
        "reason": decision.reason,
        "next_external_requirement": decision.next_external_requirement,
        "assessments": stable(list(decision.assessments)),
        "priority_queue": stable(decision.priority_queue),
        "CURRENT_PROGRAM": current.current_program,
        "CURRENT_MAX_LOCAL_EVIDENCE": current.highest_local_evidence,
        "TARGET_GAP": decision.target_gap,
        "REQUIRED_EVIDENCE": decision.required_evidence,
        "SELECTED_ACTION": decision.selected_action,
        "COMPUTATIONAL_CONTINUATION_ALLOWED": decision.computational_continuation_allowed,
        "STOP_REASON": decision.stop_reason,
    }
    return result


def _requested_compounds(package_root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted((package_root / "compounds").glob("*.json")):
        item = _load_json(path)
        result[str(item["panel_key"])] = item
    if set(result) != set(_expected_panel()):
        raise MOLDISC019Error("requested package must contain exactly the four frozen compounds")
    return result


def _load_result(result: str | Path | Mapping[str, Any]) -> tuple[dict[str, Any], Path | None]:
    if isinstance(result, Mapping):
        return dict(result), None
    path = Path(result)
    return _load_json(path), path


def validate_result(result: str | Path | Mapping[str, Any], package_root: str | Path) -> dict[str, Any]:
    """Validate a future external result without mutating state or creating evidence."""

    value, source_path = _load_result(result)
    root = Path(package_root)
    compounds = _requested_compounds(root)
    errors: list[dict[str, Any]] = []

    for field in REQUIRED_RESULT_FIELDS:
        if not _as_nonempty(value.get(field)):
            errors.append({"code": "MISSING_REQUIRED_FIELD", "field": field})
    if value.get("evidence_classification") == "TEST_SYNTHETIC" or value.get("synthetic") is True or value.get("actual_experiment") is False:
        errors.append({"code": "TEST_SYNTHETIC_NOT_SCIENTIFIC_EVIDENCE", "reason": "synthetic or non-experimental fixtures cannot become E4"})
    if value.get("actual_experiment") is not True:
        errors.append({"code": "ACTUAL_EXPERIMENT_REQUIRED", "reason": "actual_experiment=true is required for E4 eligibility"})
    if value.get("experiment_id") not in {BIOEXP001_ID, BIOEXP002_ID}:
        errors.append({"code": "UNKNOWN_EXPERIMENT_ID", "experiment_id": value.get("experiment_id")})

    panel_key = str(value.get("panel_key", ""))
    requested = compounds.get(panel_key)
    if requested is None:
        errors.append({"code": "UNKNOWN_PANEL_MEMBER", "panel_key": panel_key})
    else:
        if value.get("compound_id") != requested.get("candidate_id"):
            errors.append({"code": "EXPERIMENT_IDENTITY_MISMATCH", "field": "compound_id", "requested": requested.get("candidate_id"), "reported": value.get("compound_id")})
        if value.get("reported_inchikey_if_available") and value.get("reported_inchikey_if_available") != requested.get("inchikey"):
            errors.append({"code": "EXPERIMENT_IDENTITY_MISMATCH", "field": "reported_inchikey_if_available", "requested": requested.get("inchikey"), "reported": value.get("reported_inchikey_if_available")})
        if value.get("reported_smiles_if_available") and value.get("reported_smiles_if_available") != requested.get("canonical_isomeric_smiles"):
            errors.append({"code": "EXPERIMENT_IDENTITY_MISMATCH", "field": "reported_smiles_if_available"})
    report_file = value.get("report_file")
    if report_file and source_path:
        report_path = Path(report_file)
        if not report_path.is_absolute():
            report_path = source_path.parent / report_path
        if report_path.is_file() and value.get("report_hash") != sha256_file(report_path):
            errors.append({"code": "REPORT_HASH_MISMATCH", "report_file": str(report_path)})
    if value.get("sample_identity_method") and value.get("batch_id") in {None, ""}:
        errors.append({"code": "BATCH_ID_REQUIRED", "reason": "sample identity must be traceable to a batch"})
    if value.get("laboratory") and value.get("provider") and not str(value["laboratory"]).strip() and not str(value["provider"]).strip():
        errors.append({"code": "ATTRIBUTABLE_PROVIDER_REQUIRED"})
    guard = ExternalEvidenceIntegrator.level_guard("E2_COMPUTATIONAL", "E4_CURATED_EXPERIMENTAL", actual_experiment=value.get("actual_experiment") is True)
    eligible = not errors and guard["promotion_allowed"]
    if not guard["promotion_allowed"]:
        errors.append({"code": "EVIDENCE_LEVEL_GUARD_DENIED", "guard": guard})
    return {
        "valid": eligible,
        "eligible_for_e4": eligible,
        "evidence_level": "E4_CURATED_EXPERIMENTAL" if eligible else None,
        "errors": errors,
        "gate": guard,
        "compound_id": value.get("compound_id"),
        "panel_key": value.get("panel_key"),
        "experiment_id": value.get("experiment_id"),
        "scientific_evidence_created": False,
        "source_path": str(source_path) if source_path else None,
    }


def _affected_gap(experiment_id: str) -> str:
    if experiment_id == BIOEXP001_ID:
        return "GAP-EXPERIMENTAL-SOLUBILITY"
    if experiment_id == BIOEXP002_ID:
        return "GAP-EXPERIMENTAL-TARGET-ACTIVITY"
    return "GAP-EXPERIMENTAL-UNKNOWN"


def ingest_result(result: str | Path | Mapping[str, Any], package_root: str | Path) -> dict[str, Any]:
    """Create an append-only external update only after every result gate passes."""

    value, _ = _load_result(result)
    validation = validate_result(result, package_root)
    if not validation["eligible_for_e4"]:
        raise MOLDISC019Error("result is not eligible for E4; no update was created")
    digest = sha256_json(value)
    evidence_id = f"E4-{value['experiment_id']}-{value['panel_key']}-{digest[:12]}"
    update = ExternalEvidenceUpdate(
        update_id=f"UPDATE-{digest[:16].upper()}",
        source_id=str(value["provider"] or value["laboratory"]),
        source_version=str(value["laboratory_report_id"]),
        dataset_id_optional=None,
        evidence_ids=(evidence_id,),
        affected_claim_ids=("CLAIM-BIOLAB-PHYSICAL-FEEDBACK",),
        affected_gap_ids=(_affected_gap(str(value["experiment_id"])),),
        affected_decision_ids=("BIOLAB-NEXT-ACTION-v0.1",),
        compatibility_assessment={"identity_gate": "PASS", "protocol_recorded": True, "evidence_level": "E4_CURATED_EXPERIMENTAL"},
        conflicts=(),
        resulting_revisions=(f"BIOSTATE-{digest[:12].upper()}",),
        created_at=str(value["performed_date"]),
    )
    integrator = ExternalEvidenceIntegrator()
    integrator.add_update(update)
    state = apply_e4_feedback(default_moldisc018_state(), update)
    next_decision = evaluate_next_action(state)
    return {
        "validation": validation,
        "update": update.to_dict(),
        "updated_state": state.to_dict(),
        "recomputed_decision": next_decision.decision.to_dict(),
        "evidence_level": "E4_CURATED_EXPERIMENTAL",
        "e5_created": False,
    }


def record_first_run(config_path: str | Path, package_root: str | Path, validation_root: str | Path) -> dict[str, Any]:
    """Record the no-experiment canonical decision and transition artifact."""

    config = load_program_config_v19(config_path)
    package = prepare_package(config_path, package_root)
    decision = build_first_decision()
    validation_root = Path(validation_root)
    decision_path = validation_root / "biolab-loop-v0.1-first-decision.json"
    _write_json(decision_path, decision)
    schema_path = Path(package_root) / "external_result_schema.json"
    phase_payload = {
        "program_id": PROGRAM_ID,
        "before": "COMPUTATIONAL_MOLECULAR_DISCOVERY",
        "after": "BIOLAB_EXPERIMENTAL_FEEDBACK",
        "current_evidence": "E2_COMPUTATIONAL",
        "required_next_evidence": "E4_CURATED_EXPERIMENTAL",
        "same_level_continuation_allowed": False,
        "next_generation_allowed": False,
    }
    first_run = {
        "schema_version": "research-os.molecular-discovery.moldisc019.first-run.v1",
        "program_id": PROGRAM_ID,
        "program_version": PROGRAM_VERSION,
        "program_protocol_hash": package["program_protocol_hash"],
        "program_scientific_hash": package["program_scientific_hash"],
        "project_phase_before": "COMPUTATIONAL_MOLECULAR_DISCOVERY",
        "project_phase_after": "BIOLAB_EXPERIMENTAL_FEEDBACK",
        "biolab_loop_version": "v0.1",
        "selected_next_action": decision["selected_action"],
        "selected_target_gap": decision["target_gap"],
        "stop_reason": decision["stop_reason"],
        "required_next_evidence": decision["required_evidence"],
        "current_max_local_evidence": decision["current_max_local_evidence"],
        "computational_continuation_allowed": decision["computational_continuation_allowed"],
        "next_generation_allowed": decision["next_generation_allowed"],
        "experiment_statuses": {"BIOEXP-001": "AWAITING_EXTERNAL_PROTOCOL_OR_QUOTE", "BIOEXP-002": "PLANNED_NOT_EXECUTED"},
        "missing_external_dependencies": ["external protocol or quote", "sample identity and procurement", "eligible measurement and report"],
        "generation_executed": False,
        "new_docking_runs": 0,
        "new_molecules_generated": 0,
        "real_experiment_executed": False,
        "e4_created": False,
        "e5_created": False,
        "experimental_packet_hash": package["package"]["package_hash"],
        "result_schema_hash": sha256_file(schema_path),
        "biolab_decision_hash": sha256_json(decision),
        "phase_transition_hash": sha256_json(phase_payload),
        "knowledge_gain": "MOLDISC-019 formalizes the evidence ceiling, freezes the first physical panel, and proves an explainable stop before same-level computation.",
        "unresolved": ["no new physical panel measurement", "no experimental target activity", "no independent E5", "no closed physical loop yet"],
    }
    _write_json(validation_root / "moldisc-019-first-run-v1.json", first_run)
    return {**first_run, "decision_file": str(decision_path)}


__all__ = [
    "BIOEXP001_ID",
    "BIOEXP002_ID",
    "MOLDISC019Error",
    "PARENT_MOLDISC018_HASH",
    "PARENT_MOLDISC018_PROTOCOL_HASH",
    "PHYSICAL_LOOP_STATES",
    "PROGRAM_ID",
    "PROGRAM_VERSION",
    "REQUIRED_RESULT_FIELDS",
    "build_first_decision",
    "ingest_result",
    "load_program_config_v19",
    "package_identity",
    "package_status",
    "prepare_package",
    "program_scientific_hash",
    "protocol_hash",
    "record_first_run",
    "scientific_payload",
    "validate_result",
]
