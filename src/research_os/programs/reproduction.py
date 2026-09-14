"""End-to-end reproduction of a verified declarative Research Program.

Program reproduction is deliberately a coordinator around the existing
Program, Campaign and Experiment contracts.  It materializes frozen protocol
documents into a new root, delegates execution to ``DeclarativeProgramRunner``
and recomputes synthesis from the reproduced Campaign bundles.  It never
copies scientific outputs into the new execution and never mutates the source
root.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

import yaml

from research_os.campaigns.declarative import load_campaign_protocol
from research_os.core.hashing import sha256_file, sha256_json
from research_os.datasets import DatasetRegistry
from research_os.experiments import compare_experiment_runs
from research_os.experiments.engine import _implementation_identity
from research_os.experiments.schema import load_protocol
from research_os.programs.lineage import DeclarativeProgramRunner, verify_program_execution
from research_os.programs.store import ResearchProgramStore
from research_os.programs.synthesis import synthesize_program, verify_program_synthesis


REPRODUCTION_SCHEMA_VERSION = "research-os.program-reproduction.v1"
REPRODUCTION_ENGINE_ID = "research-os.program.reproduction.v1"


class ProgramReproductionError(ValueError):
    def __init__(self, message: str, *, first_loss: str = "PROGRAM_REPRODUCTION_RECORD_INVALID") -> None:
        super().__init__(message)
        self.first_loss = first_loss


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProgramReproductionError(f"cannot read JSON document: {path}", first_loss="PROGRAM_REPRODUCTION_SOURCE_INCOMPLETE") from exc
    if not isinstance(value, dict):
        raise ProgramReproductionError(f"JSON document must be an object: {path}", first_loss="PROGRAM_REPRODUCTION_RECORD_INVALID")
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _tree_snapshot(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise ProgramReproductionError(f"source Program root does not exist: {root}", first_loss="PROGRAM_REPRODUCTION_SOURCE_INVALID")
    files: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ProgramReproductionError(f"source tree contains a symlink: {path}", first_loss="PROGRAM_REPRODUCTION_SOURCE_INCOMPLETE")
        if path.is_file():
            files.append({"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)})
    return {"files": files, "tree_hash": sha256_json(files)}


def _current_implementation_identity() -> dict[str, Any]:
    package_root = Path(__file__).resolve().parents[3]
    files = {
        relative: sha256_file(package_root / relative)
        for relative in (
            "src/research_os/programs/lineage.py",
            "src/research_os/programs/synthesis.py",
            "src/research_os/programs/reproduction.py",
            "src/research_os/campaigns/declarative.py",
            "src/research_os/experiments/engine.py",
            "src/research_os/experiments/schema.py",
        )
    }
    return {"engine": "research_os.program_reproduction", "files": files, "sha256": sha256_json(files), "experiment_engine_sha256": _implementation_identity()["sha256"]}


def _source_experiment_implementation_gate(source_manifest: Mapping[str, Any]) -> None:
    current = _implementation_identity()["sha256"]
    for local_id, campaign in source_manifest.get("campaigns", {}).items():
        if campaign.get("status") != "COMPLETED":
            continue
        campaign_root = Path(str(campaign.get("root", "")))
        campaign_manifest = _read_json(campaign_root / "campaign-manifest.json")
        identity = campaign_manifest.get("implementation_identity", {})
        if identity.get("name") != "research_os.campaigns.declarative" or identity.get("version") != "v1":
            raise ProgramReproductionError(f"Campaign implementation is incompatible: {local_id}", first_loss="PROGRAM_REPRODUCTION_IMPLEMENTATION_MISMATCH")
        for child in campaign_manifest.get("children", {}).values():
            if child.get("status") != "COMPLETED":
                continue
            environment = _read_json(Path(str(child["root"])) / "environment.json")
            observed = environment.get("engine", {}).get("sha256")
            if observed != current:
                raise ProgramReproductionError(f"Experiment implementation differs for Campaign {local_id}", first_loss="PROGRAM_REPRODUCTION_IMPLEMENTATION_MISMATCH")


def _source_dataset_gate(source_manifest: Mapping[str, Any]) -> None:
    """Verify external dataset bytes before any reproduced child can run."""
    for local_id, campaign in source_manifest.get("campaigns", {}).items():
        if campaign.get("status") != "COMPLETED":
            continue
        campaign_manifest_path = Path(str(campaign.get("root", ""))) / "campaign-manifest.json"
        campaign_manifest = _read_json(campaign_manifest_path)
        for experiment_id, child in campaign_manifest.get("children", {}).items():
            if child.get("status") != "COMPLETED":
                continue
            run_root = Path(str(child.get("root", "")))
            manifest = _read_json(run_root / "manifest.json")
            provenance = _read_json(run_root / "provenance.json")
            expected = manifest.get("dataset", {}).get("sha256")
            if not isinstance(expected, str) or len(expected) != 64:
                raise ProgramReproductionError(
                    f"source dataset identity is incomplete: {local_id}/{experiment_id}",
                    first_loss="PROGRAM_REPRODUCTION_SOURCE_INCOMPLETE",
                )
            registry_ref = provenance.get("dataset", {}).get("registry")
            if isinstance(registry_ref, Mapping):
                registry = DatasetRegistry(root=str(registry_ref.get("registry_root", "")))
                verification = registry.verify(str(registry_ref.get("dataset_id", "")), str(registry_ref.get("version", "")))
                if verification.status != "PASS":
                    raise ProgramReproductionError(
                        f"source dataset registry verification failed: {local_id}/{experiment_id}",
                        first_loss="PROGRAM_REPRODUCTION_DATASET_IDENTITY_MISMATCH",
                    )
                registered = registry.get(str(registry_ref["dataset_id"]), str(registry_ref["version"]))
                if registered.sha256 != expected:
                    raise ProgramReproductionError(
                        f"source dataset identity changed: {local_id}/{experiment_id}",
                        first_loss="PROGRAM_REPRODUCTION_DATASET_IDENTITY_MISMATCH",
                    )
                continue
            resolved_path = provenance.get("dataset", {}).get("resolved_path")
            if not isinstance(resolved_path, str) or not Path(resolved_path).is_file() or sha256_file(resolved_path) != expected:
                raise ProgramReproductionError(
                    f"source dataset bytes changed or are unavailable: {local_id}/{experiment_id}",
                    first_loss="PROGRAM_REPRODUCTION_DATASET_IDENTITY_MISMATCH",
                )


def _materialize_child_protocol(source_path: Path, destination: Path, model_registry_root: Path) -> None:
    try:
        protocol = load_protocol(source_path)
    except Exception as exc:
        raise ProgramReproductionError(f"frozen child protocol is invalid: {source_path}", first_loss="PROGRAM_REPRODUCTION_SOURCE_INCOMPLETE") from exc
    payload = protocol.to_dict()
    model_registry = payload.get("model_registry")
    if isinstance(model_registry, Mapping) and model_registry.get("enabled"):
        payload["model_registry"] = {**dict(model_registry), "root": str(model_registry_root.resolve())}
    # CampaignRunner writes frozen child payloads using YAML serialization.  A
    # YAML suffix keeps the delegated runner from emitting YAML bytes into a
    # JSON-named file, which would make the child protocol unreadable.
    destination = destination.with_suffix(".yaml")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml.safe_dump(payload, sort_keys=True, allow_unicode=True), encoding="utf-8")


def _find_frozen_child_protocol(campaign_root: Path, experiment_id: str, fallback: Path) -> Path:
    protocol_root = campaign_root / "protocols"
    candidates = sorted(protocol_root.glob(f"{experiment_id}.*")) if protocol_root.is_dir() else []
    if candidates:
        return candidates[0]
    if fallback.is_file():
        return fallback
    raise ProgramReproductionError(f"frozen child protocol is missing: {experiment_id}", first_loss="PROGRAM_REPRODUCTION_SOURCE_INCOMPLETE")


def _materialize_protocols(source_root: Path, target_root: Path, source_manifest: Mapping[str, Any], source_plan: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    material = target_root / "material"
    program_material = material / "program.json"
    program_payload = _read_json(source_root / "program-protocol.json")
    source_campaigns = source_manifest.get("campaigns", {})
    plan_campaigns = {str(item["local_id"]): item for item in source_plan.get("campaigns", [])}
    materialized_campaigns: dict[str, Any] = {}
    for local_id in source_plan.get("execution_order", []):
        child_record = source_campaigns.get(local_id)
        if not isinstance(child_record, Mapping):
            raise ProgramReproductionError(f"declared source Campaign is missing: {local_id}", first_loss="PROGRAM_REPRODUCTION_CAMPAIGN_SET_MISMATCH")
        source_campaign_root = Path(str(child_record.get("root", "")))
        source_campaign_document = source_campaign_root / "campaign-protocol.json"
        if not source_campaign_document.is_file():
            original = Path(str(plan_campaigns.get(local_id, {}).get("protocol_path", "")))
            if not original.is_absolute():
                original = (source_root / original).resolve()
            source_campaign_document = original
        if not source_campaign_document.is_file():
            raise ProgramReproductionError(f"Campaign Protocol material is missing: {local_id}", first_loss="PROGRAM_REPRODUCTION_SOURCE_INCOMPLETE")
        campaign = load_campaign_protocol(source_campaign_document)
        campaign_destination = material / "campaigns" / local_id
        child_destination = campaign_destination / "children"
        campaign_payload = campaign.to_dict()
        for experiment in campaign_payload["experiments"]:
            experiment_id = str(experiment["experiment_id"])
            fallback = (source_campaign_document.parent / str(experiment["protocol"])).resolve()
            source_child = _find_frozen_child_protocol(source_campaign_root, experiment_id, fallback)
            child_target = child_destination / f"{experiment_id}.yaml"
            _materialize_child_protocol(source_child, child_target, material / "model-registries" / local_id / experiment_id)
            experiment["protocol"] = str(Path("children") / f"{experiment_id}.yaml")
        campaign_path = campaign_destination / "campaign.json"
        _write_json(campaign_path, campaign_payload)
        source_campaign_id = str(child_record.get("campaign_protocol_id") or plan_campaigns.get(local_id, {}).get("campaign_protocol_id"))
        if not source_campaign_id:
            raise ProgramReproductionError(f"source Campaign Protocol ID is missing: {local_id}", first_loss="PROGRAM_REPRODUCTION_SOURCE_INCOMPLETE")
        materialized_campaigns[local_id] = {"protocol_path": str(campaign_path.relative_to(material)), "campaign_protocol_id": source_campaign_id}
    program_payload["campaigns"] = [
        {
            **dict(item),
            "protocol_path": materialized_campaigns[str(item["local_id"])]["protocol_path"],
            "campaign_protocol_id": materialized_campaigns[str(item["local_id"])]["campaign_protocol_id"],
        }
        for item in program_payload.get("campaigns", [])
    ]
    _write_json(program_material, program_payload)
    return program_material, materialized_campaigns


def _bundle_evidence_ids(bundle: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for reference in bundle.get("child_evidence_refs", []):
        if isinstance(reference, str):
            result.append(reference)
        elif isinstance(reference, Mapping):
            value = reference.get("evidence_id") or reference.get("id") or reference.get("sha256")
            if isinstance(value, str):
                result.append(value)
    return result


def _prepare_reproduced_synthesis_input(source_root: Path, reproduced_root: Path) -> bool:
    source_manifest = _read_json(source_root / "program-manifest.json")
    if source_manifest.get("synthesis") is None:
        return False
    source_input_path = source_root / "synthesis-input.json"
    if not source_input_path.is_file():
        raise ProgramReproductionError("source synthesis is present but its input is missing", first_loss="PROGRAM_REPRODUCTION_SOURCE_INCOMPLETE")
    source_input = _read_json(source_input_path)
    reproduced_manifest = _read_json(reproduced_root / "program-manifest.json")
    new_entries: list[dict[str, Any]] = []
    source_entries = {str(item["local_id"]): item for item in source_input.get("campaigns", [])}
    for local_id in reproduced_manifest.get("execution_order", []):
        source_entry = source_entries.get(local_id)
        reproduced_campaign = reproduced_manifest["campaigns"].get(local_id, {})
        if not isinstance(source_entry, Mapping):
            raise ProgramReproductionError(f"source synthesis is missing Campaign input: {local_id}", first_loss="PROGRAM_REPRODUCTION_SOURCE_INCOMPLETE")
        target_entry = {"local_id": local_id, "campaign_execution_id": reproduced_campaign.get("campaign_execution_id"), "campaign_bundle_id": reproduced_campaign.get("campaign_bundle_id"), "bundle_sha256": None, "evidence": []}
        target_bundle: dict[str, Any] = {}
        if reproduced_campaign.get("root"):
            target_bundle_path = Path(str(reproduced_campaign["root"])) / "campaign-bundle.json"
            if target_bundle_path.is_file():
                target_bundle = _read_json(target_bundle_path)
                target_entry["bundle_sha256"] = sha256_file(target_bundle_path)
        old_campaign_bundle = Path(str(source_manifest["campaigns"].get(local_id, {}).get("root", ""))) / "campaign-bundle.json"
        old_ids = _bundle_evidence_ids(_read_json(old_campaign_bundle)) if old_campaign_bundle.is_file() else []
        new_ids = _bundle_evidence_ids(target_bundle)
        old_to_new = dict(zip(old_ids, new_ids))
        for evidence in source_entry.get("evidence", []):
            row = dict(evidence)
            if row.get("status") == "AVAILABLE":
                replacement = old_to_new.get(str(row.get("evidence_id")))
                if replacement is None:
                    row.pop("evidence_id", None)
                    row["status"] = "UNAVAILABLE"
                    row["contribution"] = "UNAVAILABLE"
                    row.setdefault("limitations", []).append("Reproduced Campaign did not produce the declared evidence artifact.")
                else:
                    row["evidence_id"] = replacement
            target_entry["evidence"].append(row)
        new_entries.append(target_entry)
    _write_json(reproduced_root / "synthesis-input.json", {"schema_version": source_input.get("schema_version"), "program_execution_id": reproduced_manifest["program_execution_id"], "campaigns": new_entries})
    return True


def _dataset_projection(manifest: Mapping[str, Any]) -> Any:
    dataset = manifest.get("dataset", {})
    if not isinstance(dataset, Mapping):
        return None
    registry = dataset.get("registry")
    if isinstance(registry, Mapping):
        return {key: registry.get(key) for key in ("dataset_id", "version", "scientific_dataset_id", "scientific_dataset_hash", "artifact_sha256", "record_id")}
    return {"sha256": dataset.get("sha256"), "schema_hash": dataset.get("schema_hash")}


def _model_projection(manifest: Mapping[str, Any]) -> dict[str, Any]:
    models = manifest.get("models", {})
    return {str(key): value.get("identity") for key, value in sorted(models.items()) if isinstance(value, Mapping)}


def _model_artifact_projection(manifest: Mapping[str, Any]) -> dict[str, Any]:
    registry = manifest.get("model_registry", {})
    models = registry.get("models", {}) if isinstance(registry, Mapping) else {}
    return {str(key): value.get("artifact_sha256") for key, value in sorted(models.items()) if isinstance(value, Mapping)}


def _compare_campaigns(source_root: Path, reproduced_root: Path, source_manifest: Mapping[str, Any], reproduced_manifest: Mapping[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    source_campaigns = source_manifest.get("campaigns", {})
    reproduced_campaigns = reproduced_manifest.get("campaigns", {})
    if set(source_campaigns) != set(reproduced_campaigns):
        raise ProgramReproductionError("source and reproduced Campaign sets differ", first_loss="PROGRAM_REPRODUCTION_CAMPAIGN_SET_MISMATCH")
    results: list[dict[str, Any]] = []
    all_scientific_same = True
    for local_id in source_manifest.get("execution_order", []):
        source = source_campaigns[local_id]
        reproduced = reproduced_campaigns[local_id]
        protocol_same = source.get("campaign_protocol_id") == reproduced.get("campaign_protocol_id") and source.get("campaign_protocol_hash") == reproduced.get("campaign_protocol_hash")
        execution_new = source.get("campaign_execution_id") != reproduced.get("campaign_execution_id")
        source_campaign_manifest = _read_json(Path(str(source["root"])) / "campaign-manifest.json") if source.get("root") and (Path(str(source["root"])) / "campaign-manifest.json").is_file() else {}
        reproduced_campaign_manifest = _read_json(Path(str(reproduced["root"])) / "campaign-manifest.json") if reproduced.get("root") and (Path(str(reproduced["root"])) / "campaign-manifest.json").is_file() else {}
        child_results: list[dict[str, Any]] = []
        source_children = source_campaign_manifest.get("children", {})
        reproduced_children = reproduced_campaign_manifest.get("children", {})
        if set(source_children) != set(reproduced_children):
            raise ProgramReproductionError(f"Campaign child set differs: {local_id}", first_loss="PROGRAM_REPRODUCTION_CAMPAIGN_SET_MISMATCH")
        campaign_scientific_same = protocol_same and execution_new
        for experiment_id in source_children:
            left = source_children[experiment_id]
            right = reproduced_children[experiment_id]
            same_result = False
            comparison: dict[str, Any] | None = None
            if left.get("status") == right.get("status") == "COMPLETED":
                try:
                    comparison = compare_experiment_runs(left["root"], right["root"])
                    same_result = bool(comparison.get("same_scientific_result"))
                except Exception as exc:
                    comparison = {"compatible": False, "first_loss": str(getattr(exc, "first_loss", None) or str(exc))}
                source_child_manifest = _read_json(Path(str(left["root"])) / "manifest.json")
                reproduced_child_manifest = _read_json(Path(str(right["root"])) / "manifest.json")
                child_results.append({"experiment_id": experiment_id, "source_run_id": left.get("run_id"), "reproduced_run_id": right.get("run_id"), "source_scientific_result_hash": source_child_manifest.get("scientific_result_hash"), "reproduced_scientific_result_hash": reproduced_child_manifest.get("scientific_result_hash"), "same_scientific_result": same_result, "execution_identity_different": left.get("run_id") != right.get("run_id"), "dataset_identity_same": _dataset_projection(source_child_manifest) == _dataset_projection(reproduced_child_manifest), "model_scientific_identity_same": _model_projection(source_child_manifest) == _model_projection(reproduced_child_manifest), "model_artifact_bytes_same": _model_artifact_projection(source_child_manifest) == _model_artifact_projection(reproduced_child_manifest), "comparison": comparison})
                campaign_scientific_same = campaign_scientific_same and same_result
            else:
                same_result = left.get("status") == right.get("status") and left.get("status") != "COMPLETED"
                child_results.append({"experiment_id": experiment_id, "source_status": left.get("status"), "reproduced_status": right.get("status"), "same_scientific_result": None, "execution_identity_different": left.get("run_id") != right.get("run_id")})
                campaign_scientific_same = campaign_scientific_same and same_result
            if not same_result:
                all_scientific_same = False
        all_scientific_same = all_scientific_same and campaign_scientific_same
        results.append({"local_id": local_id, "source_campaign_execution_id": source.get("campaign_execution_id"), "reproduced_campaign_execution_id": reproduced.get("campaign_execution_id"), "source_campaign_bundle_id": source.get("campaign_bundle_id"), "reproduced_campaign_bundle_id": reproduced.get("campaign_bundle_id"), "protocol_same": protocol_same, "execution_identity_different": execution_new, "source_status": source.get("status"), "reproduced_status": reproduced.get("status"), "scientific_equivalence": campaign_scientific_same, "experiments": child_results})
    return results, all_scientific_same


def _synthesis_projection(root: Path) -> dict[str, Any] | None:
    path = root / "program-synthesis.json"
    if not path.is_file():
        return None
    synthesis = _read_json(path)
    claims = {}
    for item in synthesis.get("claims", []):
        matrix = []
        for row in item.get("matrix", []):
            matrix.append({key: row.get(key) for key in ("campaign_local_id", "status", "contribution", "level", "dimensions", "negative_result", "limitations")})
        claims[str(item["local_id"])] = {"status": item.get("status"), "agreement": item.get("agreement", {}).get("consistency"), "strongest_supported_level": item.get("agreement", {}).get("strongest_supported_level"), "matrix": sorted(matrix, key=lambda row: (row["campaign_local_id"], row["status"], row["contribution"]))}
    return {"claims": claims, "conflicts": [{"claim_local_id": item.get("claim_local_id"), "campaigns": sorted(item.get("campaigns", [])), "reason": item.get("reason")} for item in synthesis.get("conflicts", [])], "unavailable": [{"claim_local_id": item.get("claim_local_id"), "campaign_local_id": item.get("campaign_local_id"), "status": item.get("status"), "contribution": item.get("contribution")} for item in synthesis.get("unavailable_evidence", [])], "strongest_supported_level": synthesis.get("strongest_supported_level"), "unresolved_uncertainty": sorted(synthesis.get("unresolved_uncertainty", []))}


def _compare_synthesis(source_root: Path, reproduced_root: Path) -> dict[str, Any]:
    source = _synthesis_projection(source_root)
    reproduced = _synthesis_projection(reproduced_root)
    if source is None and reproduced is None:
        return {"status": "NOT_PRESENT", "same_scientific_synthesis": True, "source_synthesis_id": None, "reproduced_synthesis_id": None}
    if source is None or reproduced is None:
        return {"status": "DIVERGENT", "same_scientific_synthesis": False, "source_synthesis_id": _read_json(source_root / "program-synthesis.json").get("synthesis_id") if source else None, "reproduced_synthesis_id": _read_json(reproduced_root / "program-synthesis.json").get("synthesis_id") if reproduced else None}
    source_record = _read_json(source_root / "program-synthesis.json")
    reproduced_record = _read_json(reproduced_root / "program-synthesis.json")
    same = source == reproduced
    return {"status": "MATCHED" if same else "DIVERGENT", "same_scientific_synthesis": same, "source_synthesis_id": source_record.get("synthesis_id"), "reproduced_synthesis_id": reproduced_record.get("synthesis_id"), "source_synthesis_hash": source_record.get("synthesis_hash"), "reproduced_synthesis_hash": reproduced_record.get("synthesis_hash")}


@dataclass(frozen=True)
class ProgramReproductionVerification:
    status: str
    root: str
    outcome: str | None
    first_loss: str | None
    gates: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "root": self.root, "outcome": self.outcome, "first_loss": self.first_loss, "gates": [dict(item) for item in self.gates]}


@dataclass(frozen=True)
class ResearchProgramReproductionResult:
    reproduction_id: str
    reproduction_hash: str
    status: str
    source_program_root: str
    reproduced_program_root: str | None
    source_program_protocol_id: str | None
    reproduced_program_protocol_id: str | None
    source_program_execution_id: str | None
    reproduced_program_execution_id: str | None
    source_bundle_id: str | None
    reproduced_bundle_id: str | None
    source_synthesis_id: str | None
    reproduced_synthesis_id: str | None
    source_reference_hash: str | None
    implementation_identity: Mapping[str, Any]
    structural_equivalence: bool
    scientific_equivalence: bool
    campaign_results: tuple[Mapping[str, Any], ...]
    synthesis_comparison: Mapping[str, Any]
    first_loss: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REPRODUCTION_SCHEMA_VERSION,
            "reproduction_id": self.reproduction_id,
            "reproduction_hash": self.reproduction_hash,
            "status": self.status,
            "source_program_root": self.source_program_root,
            "reproduced_program_root": self.reproduced_program_root,
            "source_program_protocol_id": self.source_program_protocol_id,
            "reproduced_program_protocol_id": self.reproduced_program_protocol_id,
            "source_program_execution_id": self.source_program_execution_id,
            "reproduced_program_execution_id": self.reproduced_program_execution_id,
            "source_bundle_id": self.source_bundle_id,
            "reproduced_bundle_id": self.reproduced_bundle_id,
            "source_synthesis_id": self.source_synthesis_id,
            "reproduced_synthesis_id": self.reproduced_synthesis_id,
            "source_reference_hash": self.source_reference_hash,
            "implementation_identity": dict(self.implementation_identity),
            "structural_equivalence": self.structural_equivalence,
            "scientific_equivalence": self.scientific_equivalence,
            "campaign_results": [dict(item) for item in self.campaign_results],
            "synthesis_comparison": dict(self.synthesis_comparison),
            "first_loss": self.first_loss,
            "created_at": self.created_at,
        }


def _make_result(payload: dict[str, Any], *, created_at: str | None = None) -> dict[str, Any]:
    digest = sha256_json(_reproduction_hash_payload(payload))
    payload["reproduction_hash"] = digest
    payload["reproduction_id"] = f"research-os.program.reproduction.v1+{digest[:16]}"
    payload["created_at"] = created_at or _now()
    return payload


def _reproduction_hash_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    canonical = {
        key: value
        for key, value in payload.items()
        if key not in {
            "reproduction_id", "reproduction_hash", "created_at",
            "source_program_root", "reproduced_program_root",
            "source_program_execution_id", "reproduced_program_execution_id",
            "source_bundle_id", "reproduced_bundle_id",
            "source_synthesis_id", "reproduced_synthesis_id", "source_reference_hash",
        }
    }
    canonical["campaign_results"] = []
    for campaign in payload.get("campaign_results", []):
        item = {
            key: value
            for key, value in campaign.items()
            if key not in {"source_campaign_execution_id", "reproduced_campaign_execution_id", "source_campaign_bundle_id", "reproduced_campaign_bundle_id"}
        }
        item["experiments"] = []
        for experiment in campaign.get("experiments", []):
            item["experiments"].append({key: value for key, value in experiment.items() if key not in {"source_run_id", "reproduced_run_id"}})
        canonical["campaign_results"].append(item)
    synthesis = payload.get("synthesis_comparison")
    if isinstance(synthesis, Mapping):
        canonical["synthesis_comparison"] = {
            key: value
            for key, value in synthesis.items()
            if key not in {"source_synthesis_id", "reproduced_synthesis_id", "source_synthesis_hash", "reproduced_synthesis_hash"}
        }
    return canonical


def _write_result(target: Path, payload: dict[str, Any]) -> dict[str, Any]:
    _write_json(target / "reproduction-manifest.json", payload)
    _write_json(target / "reproduction-report.json", payload)
    return payload


def _blocked_result(source: Path, target: Path, source_manifest: Mapping[str, Any] | None, first_loss: str, implementation: Mapping[str, Any]) -> dict[str, Any]:
    payload = {"schema_version": REPRODUCTION_SCHEMA_VERSION, "status": "BLOCKED", "source_program_root": str(source), "reproduced_program_root": str(target / "reproduced-program") if (target / "reproduced-program").exists() else None, "source_program_protocol_id": source_manifest.get("program_protocol_id") if source_manifest else None, "reproduced_program_protocol_id": None, "source_program_execution_id": source_manifest.get("program_execution_id") if source_manifest else None, "reproduced_program_execution_id": None, "source_bundle_id": (source_manifest.get("bundle") or {}).get("bundle_id") if source_manifest else None, "reproduced_bundle_id": None, "source_synthesis_id": (source_manifest.get("synthesis") or {}).get("synthesis_id") if source_manifest else None, "reproduced_synthesis_id": None, "source_reference_hash": None, "implementation_identity": dict(implementation), "structural_equivalence": False, "scientific_equivalence": False, "campaign_results": [], "synthesis_comparison": {"status": "BLOCKED"}, "first_loss": first_loss}
    return _make_result(payload)


def reproduce_program_execution(source_root: str | Path, output_root: str | Path) -> dict[str, Any]:
    source = Path(source_root).resolve()
    target = Path(output_root).resolve()
    implementation = _current_implementation_identity()
    if target.exists():
        raise ProgramReproductionError(f"reproduction target already exists: {target}", first_loss="PROGRAM_REPRODUCTION_TARGET_EXISTS")
    if source == target or source in target.parents or target in source.parents:
        raise ProgramReproductionError("source and reproduction roots must be disjoint", first_loss="PROGRAM_REPRODUCTION_PATH_INVALID")
    target.mkdir(parents=True, exist_ok=False)
    source_manifest: dict[str, Any] | None = None
    try:
        source_check = verify_program_execution(source)
        if source_check.status != "PASS":
            raise ProgramReproductionError(f"source Program verification failed: {source_check.first_loss}", first_loss="PROGRAM_REPRODUCTION_SOURCE_INVALID")
        source_manifest = _read_json(source / "program-manifest.json")
        source_plan = _read_json(source / "execution-plan.json")
        source_tree = _tree_snapshot(source)
        _source_experiment_implementation_gate(source_manifest)
        _source_dataset_gate(source_manifest)
        program_material, _ = _materialize_protocols(source, target, source_manifest, source_plan)
        reproduced_program_root = target / "reproduced-program"
        reproduced_manifest = DeclarativeProgramRunner().run(program_material, reproduced_program_root)
        reproduced_check = verify_program_execution(reproduced_program_root)
        if reproduced_check.status != "PASS":
            raise ProgramReproductionError(f"reproduced Program verification failed: {reproduced_check.first_loss}", first_loss="PROGRAM_REPRODUCTION_CHILD_BLOCKED")
        synthesis_planned = _prepare_reproduced_synthesis_input(source, reproduced_program_root)
        if synthesis_planned:
            synthesize_program(reproduced_program_root)
            synthesis_check = verify_program_synthesis(reproduced_program_root)
            if synthesis_check.status != "PASS":
                raise ProgramReproductionError(f"reproduced synthesis verification failed: {synthesis_check.first_loss}", first_loss="PROGRAM_REPRODUCTION_SYNTHESIS_DIVERGENCE")
            reproduced_manifest = _read_json(reproduced_program_root / "program-manifest.json")
        source_after = _tree_snapshot(source)
        if source_after["tree_hash"] != source_tree["tree_hash"]:
            raise ProgramReproductionError("source Program changed during reproduction", first_loss="PROGRAM_REPRODUCTION_SOURCE_MUTATED")
        structural = source_manifest["program_protocol_id"] == reproduced_manifest.get("program_protocol_id") and source_manifest["program_execution_id"] != reproduced_manifest.get("program_execution_id") and set(source_manifest.get("campaigns", {})) == set(reproduced_manifest.get("campaigns", {}))
        if not structural:
            raise ProgramReproductionError("Program or Campaign structural identity differs", first_loss="PROGRAM_REPRODUCTION_PROTOCOL_MISMATCH")
        campaign_results, children_same = _compare_campaigns(source, reproduced_program_root, source_manifest, reproduced_manifest)
        synthesis_comparison = _compare_synthesis(source, reproduced_program_root)
        scientific = children_same and bool(synthesis_comparison.get("same_scientific_synthesis"))
        outcome = "SCIENTIFICALLY_EQUIVALENT" if scientific else "DIVERGENT"
        payload = _make_result({"schema_version": REPRODUCTION_SCHEMA_VERSION, "status": outcome, "source_program_root": str(source), "reproduced_program_root": str(reproduced_program_root), "source_program_protocol_id": source_manifest.get("program_protocol_id"), "reproduced_program_protocol_id": reproduced_manifest.get("program_protocol_id"), "source_program_execution_id": source_manifest.get("program_execution_id"), "reproduced_program_execution_id": reproduced_manifest.get("program_execution_id"), "source_bundle_id": (source_manifest.get("bundle") or {}).get("bundle_id"), "reproduced_bundle_id": (reproduced_manifest.get("bundle") or {}).get("bundle_id"), "source_synthesis_id": (source_manifest.get("synthesis") or {}).get("synthesis_id"), "reproduced_synthesis_id": (reproduced_manifest.get("synthesis") or {}).get("synthesis_id"), "source_reference_hash": source_tree["tree_hash"], "implementation_identity": implementation, "structural_equivalence": structural, "scientific_equivalence": scientific, "campaign_results": campaign_results, "synthesis_comparison": synthesis_comparison, "first_loss": None})
        _write_result(target, payload)
        store = ResearchProgramStore(reproduced_program_root / "program-store.sqlite3")
        store.save_reproduction(payload, payload["created_at"])
        store.append_event(str(reproduced_manifest["program_execution_id"]), "PROGRAM_REPRODUCTION_RECORDED", {"reproduction_id": payload["reproduction_id"], "status": outcome}, payload["created_at"])
        store.close()
        _write_json(target / "source-reference.json", {"source_root": str(source), "source_tree": source_tree, "source_program_execution_id": source_manifest["program_execution_id"], "source_program_protocol_id": source_manifest["program_protocol_id"]})
        return payload
    except ProgramReproductionError as exc:
        payload = _blocked_result(source, target, source_manifest, exc.first_loss, implementation)
        _write_result(target, payload)
        return payload
    except Exception as exc:
        payload = _blocked_result(source, target, source_manifest, "PROGRAM_REPRODUCTION_RECORD_INVALID", implementation)
        payload["error"] = str(exc)
        _write_result(target, payload)
        return payload


def verify_program_reproduction(root: str | Path) -> ProgramReproductionVerification:
    target = Path(root).resolve()
    gates: list[dict[str, Any]] = []
    try:
        manifest = _read_json(target / "reproduction-manifest.json")
        if manifest.get("schema_version") != REPRODUCTION_SCHEMA_VERSION:
            raise ProgramReproductionError("unsupported reproduction schema")
        if sha256_json(_reproduction_hash_payload(manifest)) != manifest.get("reproduction_hash"):
            raise ProgramReproductionError("reproduction record hash mismatch", first_loss="PROGRAM_REPRODUCTION_RECORD_INVALID")
        source = Path(str(manifest["source_program_root"])).resolve()
        if manifest.get("status") == "BLOCKED":
            return ProgramReproductionVerification(
                "PASS",
                str(target),
                "BLOCKED",
                manifest.get("first_loss"),
                ({"rule_id": "PROGRAM-REPRODUCTION-BLOCKED", "status": "PASS", "reason": "blocked result is preserved without claiming equivalence"},),
            )
        source_check = verify_program_execution(source)
        if source_check.status != "PASS":
            raise ProgramReproductionError("source Program no longer verifies", first_loss="PROGRAM_REPRODUCTION_SOURCE_INVALID")
        reference = _read_json(target / "source-reference.json")
        if _tree_snapshot(source)["tree_hash"] != reference["source_tree"]["tree_hash"]:
            raise ProgramReproductionError("source tree changed after reproduction", first_loss="PROGRAM_REPRODUCTION_SOURCE_MUTATED")
        reproduced_root = Path(str(manifest["reproduced_program_root"]))
        reproduced_check = verify_program_execution(reproduced_root)
        if reproduced_check.status != "PASS":
            raise ProgramReproductionError("reproduced Program no longer verifies", first_loss="PROGRAM_REPRODUCTION_CHILD_BLOCKED")
        source_manifest = _read_json(source / "program-manifest.json")
        reproduced_manifest = _read_json(reproduced_root / "program-manifest.json")
        if source_manifest.get("program_protocol_id") != reproduced_manifest.get("program_protocol_id"):
            raise ProgramReproductionError("Program Protocol identity mismatch", first_loss="PROGRAM_REPRODUCTION_PROTOCOL_MISMATCH")
        if source_manifest.get("program_execution_id") == reproduced_manifest.get("program_execution_id"):
            raise ProgramReproductionError("Program Execution identity was reused", first_loss="PROGRAM_REPRODUCTION_RECORD_INVALID")
        expected = _compare_synthesis(source, reproduced_root)
        if expected != manifest.get("synthesis_comparison"):
            raise ProgramReproductionError("synthesis comparison differs from reproduction record", first_loss="PROGRAM_REPRODUCTION_SYNTHESIS_DIVERGENCE")
        expected_campaigns, children_same = _compare_campaigns(source, reproduced_root, source_manifest, reproduced_manifest)
        if expected_campaigns != manifest.get("campaign_results"):
            raise ProgramReproductionError("Campaign comparison differs from reproduction record", first_loss="PROGRAM_REPRODUCTION_RESULT_DIVERGENCE")
        scientific = children_same and bool(expected.get("same_scientific_synthesis"))
        if bool(manifest.get("scientific_equivalence")) != scientific:
            raise ProgramReproductionError("scientific equivalence flag is inconsistent", first_loss="PROGRAM_REPRODUCTION_RESULT_DIVERGENCE")
        store = ResearchProgramStore(reproduced_root / "program-store.sqlite3")
        persisted = store.get_reproduction(str(manifest["reproduction_id"]))
        store.close()
        if persisted != manifest:
            raise ProgramReproductionError("durable reproduction record differs from manifest", first_loss="PROGRAM_REPRODUCTION_RECORD_INVALID")
        gates.extend([{"rule_id": "PROGRAM-REPRODUCTION-SOURCE", "status": "PASS", "reason": "source Program and source tree verify"}, {"rule_id": "PROGRAM-REPRODUCTION-PROTOCOL", "status": "PASS", "reason": "Program Protocol matches and execution identity is new"}, {"rule_id": "PROGRAM-REPRODUCTION-LINEAGE", "status": "PASS", "reason": "Campaign and Experiment comparison matrix is reproducible"}])
        return ProgramReproductionVerification("PASS", str(target), str(manifest["status"]), manifest.get("first_loss"), tuple(gates))
    except (OSError, KeyError, TypeError, sqlite3.DatabaseError, json.JSONDecodeError, ProgramReproductionError) as exc:
        return ProgramReproductionVerification("FAIL", str(target), None, str(getattr(exc, "first_loss", None) or "PROGRAM_REPRODUCTION_RECORD_INVALID"), tuple(gates))


def inspect_program_reproduction(root: str | Path) -> dict[str, Any]:
    verification = verify_program_reproduction(root)
    manifest = _read_json(Path(root).resolve() / "reproduction-manifest.json")
    return {"verification": verification.to_dict(), **manifest}


__all__ = ["ProgramReproductionError", "ProgramReproductionVerification", "ResearchProgramReproductionResult", "inspect_program_reproduction", "reproduce_program_execution", "verify_program_reproduction"]
