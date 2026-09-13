"""Static, declarative multi-experiment campaign orchestration.

Campaigns coordinate already-declared Experiment Engine protocols.  They do
not contain model training, dataset loading, metric calculation, or model
serialization logic.  Each child remains a normal Experiment Engine package
with its own protocol, execution identity and verification boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping
import uuid

import yaml

from research_os.campaigns.models import ResearchCampaignBundle
from research_os.campaigns.store import DeclarativeCampaignStore
from research_os.core.hashing import sha256_file, sha256_json
from research_os.datasets import DatasetRegistry
from research_os.experiments import (
    ExperimentEngine,
    compare_experiment_runs,
    inspect_experiment_run,
    load_protocol,
    verify_experiment_run,
)
from research_os.experiments.engine import ExperimentExecutionError
from research_os.experiments.schema import ProtocolError, _json_object_pairs_no_duplicates, _load_yaml_strict


CAMPAIGN_PROTOCOL_ID = "research-os.campaign.protocol.v1"
CAMPAIGN_SCHEMA_VERSION = "research-os.campaign.v1"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TERMINAL_CHILD = {"COMPLETED", "FAILED", "BLOCKED", "SKIPPED_DEPENDENCY"}


class CampaignProtocolError(ValueError):
    """A campaign plan is invalid or cannot be verified fail-closed."""

    def __init__(self, message: str, *, first_loss: str = "CAMPAIGN_PROTOCOL_INVALID") -> None:
        super().__init__(message)
        self.first_loss = first_loss


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CampaignProtocolError(f"{name} must be a mapping")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CampaignProtocolError(f"{name} must be a non-empty string")
    return value.strip()


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CampaignProtocolError(f"{name} must be an integer >= {minimum}")
    return value


def _strict(value: Mapping[str, Any], allowed: set[str], required: set[str], name: str) -> None:
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise CampaignProtocolError(f"{name} has unknown keys: {', '.join(unknown)}")
    if missing:
        raise CampaignProtocolError(f"{name} is missing required keys: {', '.join(missing)}")


def _canonical_json(path: Path) -> Mapping[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            value = json.loads(text, object_pairs_hook=_json_object_pairs_no_duplicates)
            if isinstance(value, Mapping):
                return value
            raise CampaignProtocolError("campaign protocol must be a JSON/YAML mapping")
        if path.suffix.lower() in {".yaml", ".yml"}:
            value = _load_yaml_strict(text)
            if isinstance(value, Mapping):
                return value
        raise CampaignProtocolError("campaign protocol must be a JSON/YAML mapping")
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise CampaignProtocolError(f"invalid campaign protocol: {exc}") from exc


def _safe_protocol_ref(base: Path, reference: str) -> Path:
    raw = Path(reference)
    if not raw.is_absolute() and any(part == ".." for part in raw.parts):
        raise CampaignProtocolError("child protocol path traversal is not allowed", first_loss="CAMPAIGN_PROTOCOL_INVALID")
    resolved = (raw if raw.is_absolute() else base / raw).resolve()
    if not raw.is_absolute():
        try:
            resolved.relative_to(base.resolve())
        except ValueError as exc:
            raise CampaignProtocolError("child protocol symlink/path escape is not allowed") from exc
    if not resolved.is_file():
        raise CampaignProtocolError(f"child protocol does not exist: {resolved}", first_loss="CAMPAIGN_CHILD_PROTOCOL_MISSING")
    return resolved


def _scientific_experiment_payload(protocol: Any) -> dict[str, Any]:
    payload = protocol.to_dict()
    payload["dataset"] = {key: value for key, value in payload["dataset"].items() if key != "path"}
    if isinstance(payload.get("dataset_registry"), Mapping):
        payload["dataset_registry"] = {key: value for key, value in payload["dataset_registry"].items() if key != "root"}
    if isinstance(payload.get("model_registry"), Mapping):
        payload["model_registry"] = {key: value for key, value in payload["model_registry"].items() if key != "root"}
    return payload


@dataclass(frozen=True)
class CampaignExperimentSpec:
    experiment_id: str
    protocol: str
    requires: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.experiment_id):
            raise CampaignProtocolError("experiment_id must be a safe local identifier")
        if not self.protocol.strip():
            raise CampaignProtocolError("child protocol reference is required")
        if any(not _SAFE_ID.fullmatch(item) for item in self.requires):
            raise CampaignProtocolError("dependency identifiers must be safe local identifiers")
        if self.experiment_id in self.requires:
            raise CampaignProtocolError("an experiment cannot depend on itself", first_loss="CAMPAIGN_DEPENDENCY_CYCLE")

    def to_dict(self) -> dict[str, Any]:
        return {"experiment_id": self.experiment_id, "protocol": self.protocol, "requires": list(self.requires)}


@dataclass(frozen=True)
class MultiplicityPlan:
    family_id: str
    mode: str
    comparisons: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.family_id):
            raise CampaignProtocolError("analysis.multiplicity.family_id must be a safe identifier")
        if self.mode not in {"DESCRIPTIVE_ONLY", "INFERENTIAL"}:
            raise CampaignProtocolError("analysis.multiplicity.mode must be DESCRIPTIVE_ONLY or INFERENTIAL")
        for left, right in self.comparisons:
            if left == right or not _SAFE_ID.fullmatch(left) or not _SAFE_ID.fullmatch(right):
                raise CampaignProtocolError("comparisons must contain two distinct safe experiment ids", first_loss="MULTIPLICITY_PLAN_INVALID")
        object.__setattr__(self, "comparisons", tuple(sorted(self.comparisons)))
        if self.mode == "INFERENTIAL":
            raise CampaignProtocolError("INFERENTIAL multiplicity requires a separately frozen statistical contract", first_loss="MULTIPLICITY_PLAN_INVALID")

    def to_dict(self) -> dict[str, Any]:
        return {"family_id": self.family_id, "mode": self.mode, "comparisons": [list(pair) for pair in self.comparisons]}


@dataclass(frozen=True)
class CampaignProtocol:
    title: str
    domain: str
    objective: str
    hypothesis: str
    experiments: tuple[CampaignExperimentSpec, ...]
    max_runs: int
    max_failures: int
    retry_count: int
    failure_policy: str
    multiplicity: MultiplicityPlan
    source_path: Path
    schema_version: str = CAMPAIGN_SCHEMA_VERSION
    mode: str = "static"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, source_path: str | Path) -> "CampaignProtocol":
        _strict(raw, {"schema_version", "campaign", "limits", "execution", "experiments", "analysis"}, {"campaign", "limits", "execution", "experiments", "analysis"}, "campaign protocol")
        schema = str(raw.get("schema_version", CAMPAIGN_SCHEMA_VERSION))
        if schema != CAMPAIGN_SCHEMA_VERSION:
            raise CampaignProtocolError(f"unsupported campaign schema: {schema}")
        campaign = _mapping(raw["campaign"], "campaign")
        _strict(campaign, {"title", "domain", "objective", "hypothesis"}, {"title", "domain", "objective", "hypothesis"}, "campaign")
        limits = _mapping(raw["limits"], "limits")
        _strict(limits, {"max_runs", "max_failures"}, {"max_runs", "max_failures"}, "limits")
        max_runs = _integer(limits["max_runs"], "limits.max_runs", minimum=1)
        max_failures = _integer(limits["max_failures"], "limits.max_failures", minimum=0)
        execution = _mapping(raw["execution"], "execution")
        _strict(execution, {"mode", "retry_count", "failure_policy"}, {"mode", "retry_count", "failure_policy"}, "execution")
        mode = _string(execution["mode"], "execution.mode")
        if mode != "static":
            raise CampaignProtocolError("campaign execution mode must be static")
        retry_count = _integer(execution["retry_count"], "execution.retry_count", minimum=0)
        if retry_count != 0:
            raise CampaignProtocolError("campaign v1 does not permit retries", first_loss="CAMPAIGN_PROTOCOL_INVALID")
        failure_policy = _string(execution["failure_policy"], "execution.failure_policy")
        if failure_policy not in {"continue_independent", "stop_on_failure"}:
            raise CampaignProtocolError("unsupported campaign failure policy")
        experiments_raw = raw["experiments"]
        if not isinstance(experiments_raw, list) or not experiments_raw:
            raise CampaignProtocolError("experiments must be a non-empty list")
        experiments: list[CampaignExperimentSpec] = []
        for index, item in enumerate(experiments_raw):
            value = _mapping(item, f"experiments[{index}]")
            _strict(value, {"experiment_id", "protocol", "requires"}, {"experiment_id", "protocol"}, f"experiments[{index}]")
            requires = value.get("requires", ())
            if isinstance(requires, str) or not isinstance(requires, (list, tuple)):
                raise CampaignProtocolError(f"experiments[{index}].requires must be a list")
            experiments.append(CampaignExperimentSpec(_string(value["experiment_id"], f"experiments[{index}].experiment_id"), _string(value["protocol"], f"experiments[{index}].protocol"), tuple(str(item) for item in requires)))
        ids = [item.experiment_id for item in experiments]
        if len(set(ids)) != len(ids):
            raise CampaignProtocolError("experiment identifiers must be unique")
        analysis = _mapping(raw["analysis"], "analysis")
        _strict(analysis, {"multiplicity"}, {"multiplicity"}, "analysis")
        multiplicity = _mapping(analysis["multiplicity"], "analysis.multiplicity")
        _strict(multiplicity, {"family_id", "mode", "comparisons"}, {"family_id", "mode", "comparisons"}, "analysis.multiplicity")
        comparisons_raw = multiplicity["comparisons"]
        if not isinstance(comparisons_raw, list):
            raise CampaignProtocolError("analysis.multiplicity.comparisons must be a list")
        comparisons: list[tuple[str, str]] = []
        for comparison in comparisons_raw:
            if isinstance(comparison, Mapping):
                _strict(comparison, {"left", "right"}, {"left", "right"}, "comparison")
                comparisons.append((_string(comparison["left"], "comparison.left"), _string(comparison["right"], "comparison.right")))
            elif isinstance(comparison, (list, tuple)) and len(comparison) == 2:
                comparisons.append((_string(comparison[0], "comparison.left"), _string(comparison[1], "comparison.right")))
            else:
                raise CampaignProtocolError("each comparison must declare left and right", first_loss="MULTIPLICITY_PLAN_INVALID")
        if any(left not in ids or right not in ids for left, right in comparisons):
            raise CampaignProtocolError("comparison references an undeclared experiment", first_loss="MULTIPLICITY_PLAN_INVALID")
        return cls(_string(campaign["title"], "campaign.title"), _string(campaign["domain"], "campaign.domain"), _string(campaign["objective"], "campaign.objective"), _string(campaign["hypothesis"], "campaign.hypothesis"), tuple(experiments), max_runs, max_failures, retry_count, failure_policy, MultiplicityPlan(_string(multiplicity["family_id"], "analysis.multiplicity.family_id"), _string(multiplicity["mode"], "analysis.multiplicity.mode"), tuple(comparisons)), Path(source_path).resolve(), schema, mode)

    def scientific_payload(self, resolved_protocols: Mapping[str, Any] | None = None) -> dict[str, Any]:
        children = []
        for item in sorted(self.experiments, key=lambda value: value.experiment_id):
            child = {"experiment_id": item.experiment_id, "requires": sorted(item.requires)}
            if resolved_protocols and item.experiment_id in resolved_protocols:
                child["protocol_identity"] = resolved_protocols[item.experiment_id]
            else:
                child["protocol_reference"] = item.protocol
            children.append(child)
        return {
            "protocol": CAMPAIGN_PROTOCOL_ID,
            "schema_version": self.schema_version,
            "campaign": {"title": self.title, "domain": self.domain, "objective": self.objective, "hypothesis": self.hypothesis},
            "limits": {"max_runs": self.max_runs, "max_failures": self.max_failures},
            "execution": {"mode": self.mode, "retry_count": self.retry_count, "failure_policy": self.failure_policy},
            "experiments": children,
            "multiplicity": self.multiplicity.to_dict(),
        }

    def to_dict(self, *, resolved_protocols: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "campaign": {"title": self.title, "domain": self.domain, "objective": self.objective, "hypothesis": self.hypothesis},
            "limits": {"max_runs": self.max_runs, "max_failures": self.max_failures},
            "execution": {"mode": self.mode, "retry_count": self.retry_count, "failure_policy": self.failure_policy},
            "experiments": [item.to_dict() for item in self.experiments],
            "analysis": {"multiplicity": self.multiplicity.to_dict()},
        }


def load_campaign_protocol(path: str | Path) -> CampaignProtocol:
    source = Path(path).resolve()
    raw = _canonical_json(source)
    return CampaignProtocol.from_mapping(raw, source_path=source)


@dataclass(frozen=True)
class CampaignExecutionPlan:
    campaign_protocol_id: str
    campaign_protocol_hash: str
    resolved_protocols: Mapping[str, Mapping[str, Any]]
    execution_order: tuple[str, ...]
    max_runs: int
    max_failures: int
    retry_count: int
    failure_policy: str
    multiplicity: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "campaign_protocol_id": self.campaign_protocol_id,
            "campaign_protocol_hash": self.campaign_protocol_hash,
            "experiments": [dict(self.resolved_protocols[key]) for key in self.execution_order],
            "execution_order": list(self.execution_order),
            "max_runs": self.max_runs,
            "max_failures": self.max_failures,
            "retry_count": self.retry_count,
            "failure_policy": self.failure_policy,
            "multiplicity": dict(self.multiplicity),
        }
        payload["plan_hash"] = sha256_json(payload)
        return payload


@dataclass(frozen=True)
class CampaignVerification:
    status: str
    root: str
    first_loss: str | None
    gates: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "root": self.root, "first_loss": self.first_loss, "gates": [dict(item) for item in self.gates]}


def _topological_order(specs: tuple[CampaignExperimentSpec, ...]) -> tuple[str, ...]:
    by_id = {item.experiment_id: item for item in specs}
    for item in specs:
        for dependency in item.requires:
            if dependency not in by_id:
                raise CampaignProtocolError(f"missing dependency: {dependency}", first_loss="CAMPAIGN_DEPENDENCY_MISSING")
    remaining = {item.experiment_id: set(item.requires) for item in specs}
    ordered: list[str] = []
    while remaining:
        ready = sorted(key for key, deps in remaining.items() if not deps)
        if not ready:
            raise CampaignProtocolError("campaign dependency graph contains a cycle", first_loss="CAMPAIGN_DEPENDENCY_CYCLE")
        ordered.extend(ready)
        for key in ready:
            remaining.pop(key)
        for deps in remaining.values():
            deps.difference_update(ready)
    return tuple(ordered)


def _first_loss(error: Exception, fallback: str) -> str:
    return str(getattr(error, "first_loss", None) or getattr(error, "rule_id", None) or fallback)


class DeclarativeCampaignRunner:
    """Plan and execute a static campaign through the Experiment Engine."""

    def __init__(self, *, engine: ExperimentEngine | None = None) -> None:
        self.engine = engine or ExperimentEngine()

    def plan(self, protocol_path: str | Path) -> CampaignExecutionPlan:
        protocol = load_campaign_protocol(protocol_path)
        if len(protocol.experiments) > protocol.max_runs:
            raise CampaignProtocolError("declared experiments exceed max_runs", first_loss="CAMPAIGN_RUN_LIMIT_EXCEEDED")
        order = _topological_order(protocol.experiments)
        by_id = {item.experiment_id: item for item in protocol.experiments}
        resolved: dict[str, Mapping[str, Any]] = {}
        identities: dict[str, str] = {}
        for local_id in order:
            spec = by_id[local_id]
            child_path = _safe_protocol_ref(protocol.source_path.parent, spec.protocol)
            try:
                child = load_protocol(child_path)
            except Exception as exc:
                raise CampaignProtocolError(f"child protocol is invalid for {local_id}: {exc}", first_loss="CAMPAIGN_CHILD_PROTOCOL_INVALID") from exc
            child_identity = sha256_json(_scientific_experiment_payload(child))
            identities[local_id] = f"research-os.experiment.protocol.v1+{child_identity[:16]}"
            registry_ref = None
            if child.dataset_registry is not None and child.dataset_registry.enabled:
                root = Path(child.dataset_registry.root)
                if not root.is_absolute():
                    root = (child_path.parent / root).resolve()
                registry = DatasetRegistry(root=root)
                try:
                    verification = registry.verify(child.dataset_registry.dataset_id, child.dataset_registry.version)
                except Exception as exc:
                    raise CampaignProtocolError(f"dataset verification failed for {local_id}: {exc}", first_loss="CAMPAIGN_DATASET_VERIFICATION_FAILED") from exc
                if verification.status != "PASS":
                    raise CampaignProtocolError(f"dataset verification failed for {local_id}: {verification.first_loss}", first_loss="CAMPAIGN_DATASET_VERIFICATION_FAILED")
                dataset = registry.get(child.dataset_registry.dataset_id, child.dataset_registry.version)
                record = registry.get_record(child.dataset_registry.dataset_id, child.dataset_registry.version)
                registry_ref = {
                    "registry_root": str(root),
                    "dataset_id": dataset.dataset_id,
                    "version": dataset.version,
                    "scientific_dataset_id": dataset.scientific_dataset_id,
                    "scientific_dataset_hash": dataset.scientific_dataset_hash,
                    "artifact_sha256": dataset.sha256,
                    "record_id": record.record_id,
                }
            resolved[local_id] = {
                "experiment_id": local_id,
                "protocol_id": child.protocol,
                "protocol_identity": identities[local_id],
                "protocol_hash": sha256_json(child.to_dict()),
                "protocol_path": str(child_path),
                "requires": list(by_id[local_id].requires),
                "dataset_registry": registry_ref,
                "experiment_engine_id": child.protocol,
            }
        campaign_payload = protocol.scientific_payload(identities)
        campaign_hash = sha256_json(campaign_payload)
        return CampaignExecutionPlan(f"research-os.campaign.protocol.v1+{campaign_hash[:16]}", campaign_hash, resolved, order, protocol.max_runs, protocol.max_failures, protocol.retry_count, protocol.failure_policy, protocol.multiplicity.to_dict())

    def run(self, protocol_path: str | Path, output_root: str | Path) -> dict[str, Any]:
        plan = self.plan(protocol_path)
        root = Path(output_root).resolve()
        if root.exists():
            raise CampaignProtocolError(f"campaign output already exists: {root}", first_loss="CAMPAIGN_OUTPUT_EXISTS")
        root.mkdir(parents=True, exist_ok=False)
        experiments_root = root / "experiments"
        experiments_root.mkdir()
        frozen_protocols_root = root / "protocols"
        frozen_protocols_root.mkdir()
        frozen_resolved: dict[str, Mapping[str, Any]] = {}
        for local_id in plan.execution_order:
            source = Path(plan.resolved_protocols[local_id]["protocol_path"])
            destination = frozen_protocols_root / f"{local_id}{source.suffix.lower()}"
            child_protocol = load_protocol(source)
            frozen_payload = child_protocol.to_dict()
            dataset_path = Path(child_protocol.dataset.path)
            if not dataset_path.is_absolute():
                frozen_payload["dataset"]["path"] = str((source.parent / dataset_path).resolve())
            if isinstance(frozen_payload.get("dataset_registry"), Mapping) and frozen_payload["dataset_registry"].get("enabled"):
                registry_root = Path(str(frozen_payload["dataset_registry"]["root"]))
                if not registry_root.is_absolute():
                    frozen_payload["dataset_registry"]["root"] = str((source.parent / registry_root).resolve())
            if isinstance(frozen_payload.get("model_registry"), Mapping) and frozen_payload["model_registry"].get("enabled"):
                model_root = Path(str(frozen_payload["model_registry"]["root"]))
                if not model_root.is_absolute():
                    frozen_payload["model_registry"]["root"] = str((source.parent / model_root).resolve())
            destination.write_text(yaml.safe_dump(frozen_payload, sort_keys=True, allow_unicode=True), encoding="utf-8")
            frozen_resolved[local_id] = {**plan.resolved_protocols[local_id], "execution_protocol_path": str(destination.resolve())}
        plan = CampaignExecutionPlan(plan.campaign_protocol_id, plan.campaign_protocol_hash, frozen_resolved, plan.execution_order, plan.max_runs, plan.max_failures, plan.retry_count, plan.failure_policy, plan.multiplicity)
        protocol = load_campaign_protocol(protocol_path)
        execution_id = f"research-os.campaign.execution.v1+{uuid.uuid4().hex}"
        store = DeclarativeCampaignStore(root / "campaign-execution.sqlite3")
        started = _now()
        children = {
            item: {
                "experiment_id": item,
                "protocol_id": plan.resolved_protocols[item]["protocol_id"],
                "protocol_identity": plan.resolved_protocols[item]["protocol_identity"],
                "requires": list(plan.resolved_protocols[item]["requires"]),
                "status": "PLANNED",
                "attempts": 0,
                "first_loss": None,
                "run_id": None,
                "root": None,
                "dataset_registry": plan.resolved_protocols[item]["dataset_registry"],
                "model_registry": None,
            }
            for item in plan.execution_order
        }
        manifest: dict[str, Any] = {
            "schema_version": "research-os.campaign-execution.v1",
            "campaign_protocol_id": plan.campaign_protocol_id,
            "campaign_protocol_hash": plan.campaign_protocol_hash,
            "campaign_execution_id": execution_id,
            "source_path": str(Path(protocol_path).resolve()),
            "campaign_execution_started": False,
            "status": "PLANNED",
            "implementation_identity": {"name": "research_os.campaigns.declarative", "version": "v1"},
            "created_at": started,
            "updated_at": started,
            "retry_count": 0,
            "failure_policy": plan.failure_policy,
            "max_runs": plan.max_runs,
            "max_failures": plan.max_failures,
            "multiplicity": plan.multiplicity,
            "execution_order": list(plan.execution_order),
            "children": children,
            "failures": 0,
            "analysis": None,
            "bundle": None,
        }
        self._write_snapshot(root, manifest, plan, store)
        manifest["campaign_execution_started"] = True
        manifest["status"] = "RUNNING"
        manifest["updated_at"] = _now()
        self._write_snapshot(root, manifest, plan, store)
        for local_id in plan.execution_order:
            child = children[local_id]
            if any(children[dep]["status"] != "COMPLETED" for dep in child["requires"]):
                child.update(status="SKIPPED_DEPENDENCY", first_loss="CHILD_DEPENDENCY_FAILED")
                self._record_child(store, execution_id, child)
                self._write_snapshot(root, manifest, plan, store)
                continue
            if manifest["failures"] > 0 and manifest["failures"] >= plan.max_failures and plan.failure_policy == "continue_independent":
                child.update(status="BLOCKED", first_loss="CAMPAIGN_FAILURE_LIMIT_EXCEEDED")
                self._record_child(store, execution_id, child)
                self._write_snapshot(root, manifest, plan, store)
                continue
            child["status"] = "RUNNING"
            child["attempts"] = 1
            self._record_child(store, execution_id, child)
            self._write_snapshot(root, manifest, plan, store)
            child_root = experiments_root / local_id
            child_root.mkdir()
            try:
                result = self.engine.run(plan.resolved_protocols[local_id]["execution_protocol_path"], child_root)
                verify_experiment_run(result.root)
                child_manifest = json.loads((Path(result.root) / "manifest.json").read_text(encoding="utf-8"))
                child.update(status="COMPLETED", root=str(Path(result.root).resolve()), run_id=f"research-os.experiment.run.v1+{result.execution_hash[:16]}", scientific_result_hash=result.scientific_result_hash, model_registry=child_manifest.get("model_registry"), evidence_refs=[{"path": str((Path(result.root) / "evidence.json").resolve()), "sha256": sha256_file(Path(result.root) / "evidence.json")}])
            except Exception as exc:  # a child failure is recorded, never retried
                manifest["failures"] += 1
                child.update(status="FAILED", root=str(child_root.resolve()), first_loss=_first_loss(exc, "CHILD_EXPERIMENT_FAILED"), error=str(exc))
            self._record_child(store, execution_id, child)
            manifest["updated_at"] = _now()
            self._write_snapshot(root, manifest, plan, store)
            if child["status"] == "FAILED" and plan.failure_policy == "stop_on_failure":
                for remaining in plan.execution_order[plan.execution_order.index(local_id) + 1:]:
                    if children[remaining]["status"] == "PLANNED":
                        children[remaining].update(status="BLOCKED", first_loss="CHILD_EXPERIMENT_FAILED")
                        self._record_child(store, execution_id, children[remaining])
                break
        completed = all(item["status"] == "COMPLETED" for item in children.values())
        manifest["status"] = "COMPLETED" if completed else ("FAILED" if all(item["status"] == "FAILED" for item in children.values()) else "PARTIAL")
        analysis = _analyze_campaign(root, manifest)
        manifest["analysis"] = analysis
        bundle = _make_bundle(manifest, root)
        manifest["bundle"] = bundle
        manifest["updated_at"] = _now()
        self._write_snapshot(root, manifest, plan, store)
        store.append_event(execution_id, "CAMPAIGN_COMPLETED", {"status": manifest["status"], "failures": manifest["failures"]}, manifest["updated_at"])
        store.close()
        return manifest

    @staticmethod
    def _record_child(store: DeclarativeCampaignStore, execution_id: str, child: dict[str, Any]) -> None:
        store.append_child(execution_id, str(child["experiment_id"]), int(child.get("attempts", 0)), str(child["status"]), dict(child), _now())

    @staticmethod
    def _write_snapshot(root: Path, manifest: dict[str, Any], plan: CampaignExecutionPlan, store: DeclarativeCampaignStore) -> None:
        plan_path = root / "execution-plan.json"
        if not plan_path.exists():
            plan_path.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        protocol_path = root / "campaign-protocol.json"
        if not protocol_path.exists():
            protocol_path.write_text(json.dumps(load_campaign_protocol(manifest.get("source_path", root)).to_dict() if manifest.get("source_path") else {"campaign_protocol_id": plan.campaign_protocol_id}, indent=2, sort_keys=True), encoding="utf-8")
        manifest["campaign_protocol_document_hash"] = sha256_file(protocol_path)
        manifest["execution_plan_hash"] = json.loads(plan_path.read_text(encoding="utf-8")).get("plan_hash")
        payload = dict(manifest)
        payload.pop("record_hash", None)
        manifest["record_hash"] = sha256_json(payload)
        (root / "campaign-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        store.save_snapshot(manifest)


def _analyze_campaign(root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    children = manifest["children"]
    comparisons: list[dict[str, Any]] = []
    declared = manifest["multiplicity"]["comparisons"]
    for left, right in declared:
        lhs, rhs = children[left], children[right]
        item: dict[str, Any] = {"left": left, "right": right, "status": "UNAVAILABLE"}
        if lhs["status"] == rhs["status"] == "COMPLETED":
            try:
                item.update({"status": "COMPLETED", "result": compare_experiment_runs(lhs["root"], rhs["root"])})
            except Exception as exc:
                item.update({"status": "NOT_COMPARABLE", "first_loss": _first_loss(exc, "CAMPAIGN_COMPARISON_FAILED")})
        else:
            item["first_loss"] = "CHILD_RESULT_UNAVAILABLE"
        comparisons.append(item)
    return {
        "schema_version": "research-os.campaign-analysis.v1",
        "campaign_execution_id": manifest["campaign_execution_id"],
        "campaign_protocol_id": manifest["campaign_protocol_id"],
        "child_status": {key: value["status"] for key, value in children.items()},
        "comparisons": comparisons,
        "multiplicity": {**manifest["multiplicity"], "declared_comparison_count": len(declared), "inferential_claims": []},
        "scientific_status": "UNASSESSED",
        "evidence_level": "E2_COMPUTATIONAL",
        "interpretation": "Execution and comparison records are preserved; campaign completion does not imply hypothesis support or Evidence Level promotion.",
    }


def _make_bundle(manifest: Mapping[str, Any], root: Path) -> dict[str, Any]:
    child_runs = tuple(value["run_id"] for value in manifest["children"].values() if value.get("run_id"))
    dataset_ids = tuple(value["dataset_registry"]["dataset_id"] for value in manifest["children"].values() if value.get("dataset_registry"))
    model_ids = tuple(value["model_registry"]["models"][key]["record_id"] for value in manifest["children"].values() if isinstance(value.get("model_registry"), Mapping) for key in value["model_registry"].get("models", {}))
    bundle_seed = {"execution": manifest["campaign_execution_id"], "children": child_runs}
    bundle_id = f"research-os.campaign.bundle.v1+{sha256_json(bundle_seed)[:16]}"
    extras = {
        "child_evidence_refs": [ref for value in manifest["children"].values() for ref in value.get("evidence_refs", [])],
        "comparison_outputs": manifest["analysis"].get("comparisons", []),
        "multiplicity": manifest["analysis"].get("multiplicity", {}),
    }
    bundle = ResearchCampaignBundle(manifest["campaign_execution_id"], bundle_id, child_runs, (), (), (), (), str(root / "analysis-manifest.json"), "Declarative campaign execution bundle; scientific status remains unassessed.", "pending", dataset_ids=dataset_ids, model_ids=model_ids, phase_id="DECLARATIVE-CAMPAIGN-V1").to_dict()
    bundle.update(extras)
    bundle["bundle_hash"] = sha256_json({key: value for key, value in bundle.items() if key != "bundle_hash"})
    (root / "analysis-manifest.json").write_text(json.dumps(manifest["analysis"], indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    (root / "campaign-bundle.json").write_text(json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return bundle


def verify_campaign_execution(root: str | Path) -> CampaignVerification:
    target = Path(root).resolve()
    gates: list[dict[str, Any]] = []
    try:
        manifest_path = target / "campaign-manifest.json"
        plan_path = target / "execution-plan.json"
        if not target.is_dir() or not manifest_path.is_file() or not plan_path.is_file():
            raise CampaignProtocolError("campaign execution package is incomplete", first_loss="CAMPAIGN_RECORD_MISSING")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if sha256_json({key: value for key, value in plan.items() if key != "plan_hash"}) != plan.get("plan_hash"):
            raise CampaignProtocolError("execution plan hash mismatch", first_loss="CAMPAIGN_PLAN_HASH_MISMATCH")
        protocol_document = target / "campaign-protocol.json"
        if not protocol_document.is_file() or sha256_file(protocol_document) != manifest.get("campaign_protocol_document_hash"):
            raise CampaignProtocolError("campaign protocol document hash mismatch", first_loss="CAMPAIGN_PROTOCOL_HASH_MISMATCH")
        CampaignProtocol.from_mapping(json.loads(protocol_document.read_text(encoding="utf-8")), source_path=protocol_document)
        if manifest.get("execution_plan_hash") != plan.get("plan_hash"):
            raise CampaignProtocolError("campaign execution plan reference mismatch", first_loss="CAMPAIGN_PLAN_HASH_MISMATCH")
        if sha256_json({key: value for key, value in manifest.items() if key != "record_hash"}) != manifest.get("record_hash"):
            raise CampaignProtocolError("campaign record hash mismatch", first_loss="CAMPAIGN_RECORD_HASH_MISMATCH")
        if manifest.get("campaign_protocol_id") != plan.get("campaign_protocol_id"):
            raise CampaignProtocolError("campaign protocol identity differs from execution plan")
        declared = set(plan.get("execution_order", []))
        children = manifest.get("children")
        if not isinstance(children, Mapping) or set(children) != declared:
            raise CampaignProtocolError("declared and observed child experiments differ", first_loss="CAMPAIGN_CHILD_SET_MISMATCH")
        experiments_root = target / "experiments"
        actual_dirs = {item.name for item in experiments_root.iterdir()} if experiments_root.is_dir() else set()
        if actual_dirs - declared:
            raise CampaignProtocolError("undeclared child experiment directory exists", first_loss="CAMPAIGN_UNDECLARED_RUN")
        if manifest.get("campaign_execution_started") is not True:
            raise CampaignProtocolError("campaign execution was never started")
        plan_children = {item["experiment_id"]: item for item in plan.get("experiments", [])}
        for local_id, child in children.items():
            if child.get("status") not in _TERMINAL_CHILD:
                raise CampaignProtocolError(f"child {local_id} has no terminal status", first_loss="CAMPAIGN_CHILD_INCOMPLETE")
            if int(child.get("attempts", 0)) > 1:
                raise CampaignProtocolError(f"child {local_id} has an implicit retry", first_loss="CAMPAIGN_RETRY_NOT_ALLOWED")
            dependencies = child.get("requires", [])
            if child.get("status") == "COMPLETED" and any(children.get(dependency, {}).get("status") != "COMPLETED" for dependency in dependencies):
                raise CampaignProtocolError(f"child {local_id} completed despite failed dependency", first_loss="CHILD_DEPENDENCY_FAILED")
            if child.get("status") == "COMPLETED":
                if not child.get("root"):
                    raise CampaignProtocolError(f"completed child {local_id} has no run root")
                result = verify_experiment_run(child["root"])
                child_manifest = json.loads((Path(child["root"]) / "manifest.json").read_text(encoding="utf-8"))
                expected_registry = plan_children.get(local_id, {}).get("dataset_registry")
                observed_registry = child_manifest.get("dataset", {}).get("registry") if isinstance(child_manifest.get("dataset"), Mapping) else None
                registry_keys = ("registry_root", "dataset_id", "version", "scientific_dataset_id", "record_id", "artifact_sha256")
                registry_matches = expected_registry and observed_registry and all(expected_registry.get(key) == observed_registry.get(key) for key in registry_keys)
                if (expected_registry or observed_registry) and not registry_matches:
                    raise CampaignProtocolError(f"child {local_id} dataset provenance differs from the static plan", first_loss="CAMPAIGN_DATASET_IDENTITY_MISMATCH")
                expected_run = f"research-os.experiment.run.v1+{child_manifest['execution_hash'][:16]}"
                if child.get("run_id") != expected_run or child.get("scientific_result_hash") != child_manifest.get("scientific_result_hash"):
                    raise CampaignProtocolError(f"child {local_id} identity mismatch", first_loss="CHILD_RUN_IDENTITY_MISMATCH")
                gates.append({"rule_id": "CAMPAIGN-CHILD-VERIFIED", "status": "PASS", "child": local_id, "reason": result.status})
        analysis_path = target / "analysis-manifest.json"
        if not analysis_path.is_file() or not isinstance(manifest.get("analysis"), Mapping):
            raise CampaignProtocolError("campaign analysis manifest is missing")
        if json.loads(analysis_path.read_text(encoding="utf-8")) != manifest["analysis"]:
            raise CampaignProtocolError("campaign analysis manifest mismatch")
        bundle_path = target / "campaign-bundle.json"
        if not bundle_path.is_file() or json.loads(bundle_path.read_text(encoding="utf-8")) != manifest.get("bundle"):
            raise CampaignProtocolError("campaign bundle is missing or inconsistent", first_loss="CAMPAIGN_BUNDLE_MISMATCH")
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_identity = {key: value for key, value in bundle.items() if key != "bundle_hash"}
        if sha256_json(bundle_identity) != bundle.get("bundle_hash"):
            raise CampaignProtocolError("campaign bundle hash mismatch", first_loss="CAMPAIGN_BUNDLE_MISMATCH")
        if manifest["analysis"].get("multiplicity", {}).get("declared_comparison_count") != len(manifest["multiplicity"].get("comparisons", [])):
            raise CampaignProtocolError("multiplicity disclosure is incomplete", first_loss="MULTIPLICITY_PLAN_INVALID")
        gates.extend([
            {"rule_id": "CAMPAIGN-PLAN-FROZEN", "status": "PASS", "reason": "campaign protocol and child declaration are immutable for this execution"},
            {"rule_id": "CAMPAIGN-NO-UNDECLARED-RUNS", "status": "PASS", "reason": "observed child roots match the static plan"},
            {"rule_id": "CAMPAIGN-MULTIPLICITY", "status": "PASS", "reason": "all preregistered comparisons are disclosed"},
            {"rule_id": "CAMPAIGN-EVIDENCE-BOUNDARY", "status": "PASS", "reason": "campaign summary remains E2_COMPUTATIONAL and scientific status is not inferred"},
        ])
        return CampaignVerification("PASS", str(target), None, tuple(gates))
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ProtocolError, ExperimentExecutionError, CampaignProtocolError) as exc:
        return CampaignVerification("FAIL", str(target), _first_loss(exc, "CAMPAIGN_VERIFICATION_FAILED"), tuple(gates))


def inspect_campaign_execution(root: str | Path) -> dict[str, Any]:
    verification = verify_campaign_execution(root)
    target = Path(root).resolve()
    manifest = json.loads((target / "campaign-manifest.json").read_text(encoding="utf-8"))
    return {"verification": verification.to_dict(), "campaign_protocol_id": manifest.get("campaign_protocol_id"), "campaign_execution_id": manifest.get("campaign_execution_id"), "status": manifest.get("status"), "execution_order": manifest.get("execution_order"), "children": manifest.get("children"), "multiplicity": manifest.get("multiplicity"), "analysis": manifest.get("analysis"), "bundle": manifest.get("bundle")}


__all__ = [
    "CAMPAIGN_PROTOCOL_ID",
    "CAMPAIGN_SCHEMA_VERSION",
    "CampaignExperimentSpec",
    "CampaignExecutionPlan",
    "CampaignProtocol",
    "CampaignProtocolError",
    "CampaignVerification",
    "DeclarativeCampaignRunner",
    "inspect_campaign_execution",
    "load_campaign_protocol",
    "verify_campaign_execution",
]
