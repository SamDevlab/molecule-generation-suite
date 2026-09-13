from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import sys
import tempfile
from typing import Any, Mapping

import yaml

from research_os.core.hashing import sha256_file, sha256_json
from research_os.artifacts import ModelArtifactManifest
from research_os.experiments.registry import ExperimentExecutionError, ExperimentRegistry
from research_os.experiments.schema import PROTOCOL_ID, ExperimentProtocol, load_protocol
from research_os.ml.registry import ModelRegistry


REQUIRED_ARTIFACTS = (
    "manifest.json",
    "protocol.yaml",
    "metrics.json",
    "provenance.json",
    "evidence.json",
    "environment.json",
    "hashes.json",
    "report.md",
)
OPTIONAL_ARTIFACTS = ("model-registry.json",)
_IMPLEMENTATION_FILES = ("__init__.py", "engine.py", "registry.py", "schema.py")


@dataclass(frozen=True)
class ExperimentRunResult:
    root: str
    experiment_id: str
    scientific_result_hash: str
    execution_hash: str
    compatibility_hash: str
    metrics: Mapping[str, Mapping[str, float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "experiment_id": self.experiment_id,
            "scientific_result_hash": self.scientific_result_hash,
            "execution_hash": self.execution_hash,
            "compatibility_hash": self.compatibility_hash,
            "metrics": {name: dict(values) for name, values in self.metrics.items()},
        }


@dataclass(frozen=True)
class VerificationResult:
    status: str
    root: str
    scientific_result_hash: str | None
    execution_hash: str | None
    gates: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "root": self.root,
            "scientific_result_hash": self.scientific_result_hash,
            "execution_hash": self.execution_hash,
            "gates": [dict(gate) for gate in self.gates],
        }


@dataclass(frozen=True)
class ExperimentReproductionResult:
    source_root: str
    reproduced_root: str
    source_scientific_result_hash: str
    scientific_result_hash: str
    compatibility_hash: str
    implementation_hash: str
    status: str = "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_root": self.source_root,
            "reproduced_root": self.reproduced_root,
            "source_scientific_result_hash": self.source_scientific_result_hash,
            "scientific_result_hash": self.scientific_result_hash,
            "same_scientific_result": self.source_scientific_result_hash == self.scientific_result_hash,
            "compatibility_hash": self.compatibility_hash,
            "implementation_hash": self.implementation_hash,
        }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExperimentExecutionError(f"cannot read JSON artifact {path.name}: {exc}") from exc


def _implementation_identity() -> dict[str, Any]:
    package = Path(__file__).resolve().parent
    files = {name: sha256_file(package / name) for name in _IMPLEMENTATION_FILES}
    return {
        "name": "research_os.experiments",
        "protocol": PROTOCOL_ID,
        "files": files,
        "sha256": sha256_json(files),
    }


def _environment() -> dict[str, Any]:
    implementation = _implementation_identity()
    return {
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "engine": {
            **implementation,
            "python_cache_tag": getattr(sys.implementation, "cache_tag", None),
        },
    }


def _scientific_protocol_payload(protocol: ExperimentProtocol) -> dict[str, Any]:
    """Return only declared scientific choices, excluding labels and file locations."""
    return {
        "protocol": protocol.protocol,
        "task": protocol.experiment.task,
        "seed": protocol.experiment.seed,
        "dataset": {
            "adapter": protocol.dataset.adapter,
            "target": protocol.dataset.target,
            "features": list(protocol.dataset.features),
        },
        "split": protocol.split.to_dict(),
        "models": [model.to_dict() for model in protocol.models],
        "metrics": list(protocol.metrics),
    }


def _compatibility_payload(protocol: ExperimentProtocol) -> dict[str, Any]:
    """Return methodological choices that must match before metric comparison.

    Seed is intentionally excluded so fixed-method replication runs can be compared.
    """
    payload = _scientific_protocol_payload(protocol)
    payload.pop("seed")
    return payload


def _scientific_payload(
    *,
    scientific_protocol_hash: str,
    dataset_hash: str,
    schema_hash: str,
    split_hash: str,
    model_identities: Mapping[str, str],
    metrics: Mapping[str, Mapping[str, float]],
) -> dict[str, Any]:
    return {
        "scientific_protocol_hash": scientific_protocol_hash,
        "dataset_hash": dataset_hash,
        "dataset_schema_hash": schema_hash,
        "split_membership_hash": split_hash,
        "model_identities": dict(sorted(model_identities.items())),
        "metrics": {model: dict(sorted(values.items())) for model, values in sorted(metrics.items())},
    }


def _report(manifest: Mapping[str, Any], metrics: Mapping[str, Mapping[str, float]]) -> str:
    lines = [
        f"# Declarative experiment: {manifest['experiment_id']}",
        "",
        f"- Protocol: `{manifest['protocol']}`",
        f"- Status: **{manifest['status']}**",
        f"- Dataset rows: {manifest['dataset']['row_count']}",
        f"- Dataset SHA-256: `{manifest['dataset']['sha256']}`",
        f"- Split membership SHA-256: `{manifest['split']['membership_hash']}`",
        f"- Scientific protocol SHA-256: `{manifest['scientific_protocol_hash']}`",
        f"- Scientific result SHA-256: `{manifest['scientific_result_hash']}`",
        f"- Execution SHA-256: `{manifest['execution_hash']}`",
        "",
        "## Metrics",
        "",
        "| Model | Metric | Value |",
        "| --- | --- | ---: |",
    ]
    for model_id, values in metrics.items():
        for metric_id, value in values.items():
            lines.append(f"| `{model_id}` | `{metric_id}` | {value:.12g} |")
    lines.extend([
        "",
        "## Interpretation boundary",
        "",
        "This report records the declared computation and its integrity identities. It does not infer domain-specific scientific meaning beyond the protocol.",
        "",
    ])
    return "\n".join(lines)


class ExperimentEngine:
    def __init__(self, registry: ExperimentRegistry | None = None) -> None:
        self.registry = registry or ExperimentRegistry()

    def run(self, protocol_path: str | Path, output_root: str | Path = "runs") -> ExperimentRunResult:
        protocol = load_protocol(protocol_path)
        dataset_adapter = self.registry.dataset(protocol.dataset.adapter)
        split_strategy = self.registry.split(protocol.split.strategy)
        metric_functions = {metric_id: self.registry.metric(metric_id) for metric_id in protocol.metrics}
        model_adapters = {model.id: self.registry.model(model.adapter) for model in protocol.models}

        table = dataset_adapter.load(protocol.dataset, protocol.source_path)
        split = split_strategy.split(table.row_count, protocol.split, protocol.experiment.seed)
        train_x = [table.features[index] for index in split.train_indices]
        train_y = [table.target[index] for index in split.train_indices]
        test_x = [table.features[index] for index in split.test_indices]
        test_y = [table.target[index] for index in split.test_indices]

        metrics: dict[str, dict[str, float]] = {}
        model_identities: dict[str, str] = {}
        fitted_parameters: dict[str, Mapping[str, Any]] = {}
        for model in protocol.models:
            result = model_adapters[model.id].fit_predict(train_x, train_y, test_x, model)
            model_identities[model.id] = result.model_identity
            fitted_parameters[model.id] = result.fitted_parameters
            values: dict[str, float] = {}
            for metric_id, metric in metric_functions.items():
                value = float(metric(test_y, result.predictions))
                if not math.isfinite(value):
                    raise ExperimentExecutionError(f"metric {metric_id} produced a non-finite result")
                values[metric_id] = value
            metrics[model.id] = values

        protocol_payload = protocol.to_dict()
        protocol_hash = sha256_json(protocol_payload)
        scientific_protocol_hash = sha256_json(_scientific_protocol_payload(protocol))
        compatibility_payload = _compatibility_payload(protocol)
        compatibility_hash = sha256_json(compatibility_payload)
        scientific_payload = _scientific_payload(
            scientific_protocol_hash=scientific_protocol_hash,
            dataset_hash=table.dataset_hash,
            schema_hash=table.schema_hash,
            split_hash=split.membership_hash,
            model_identities=model_identities,
            metrics=metrics,
        )
        scientific_result_hash = sha256_json(scientific_payload)
        environment = _environment()
        execution_hash = sha256_json({"scientific_result_hash": scientific_result_hash, "environment": environment})
        created_at = datetime.now(timezone.utc).isoformat()

        target = Path(output_root) / protocol.experiment.id
        if target.exists():
            raise ExperimentExecutionError(f"run target already exists: {target}")
        target.mkdir(parents=True, exist_ok=False)

        model_registry_refs: dict[str, dict[str, Any]] = {}
        model_registry_root: Path | None = None
        if protocol.model_registry is not None and protocol.model_registry.enabled:
            model_registry_root = Path(protocol.model_registry.root)
            if not model_registry_root.is_absolute():
                model_registry_root = (protocol.source_path.parent / model_registry_root).resolve()
            model_registry = ModelRegistry(root=model_registry_root)
            dataset_identity = f"dataset-sha256:{table.dataset_hash}"
            environment_identity = sha256_json(environment)
            with tempfile.TemporaryDirectory(prefix="research-os-model-registration-") as temporary:
                for model in protocol.models:
                    artifact_path = Path(temporary) / f"{model.id}.json"
                    _write_json(artifact_path, {
                        "schema": "research-os.declarative-model-artifact.v1",
                        "model_id": model.id,
                        "adapter": model.adapter,
                        "model_identity": model_identities[model.id],
                        "fitted_parameters": fitted_parameters[model.id],
                    })
                    model_manifest = ModelArtifactManifest.from_model_file(
                        model_id=f"{protocol.experiment.id}:{model.id}",
                        task=protocol.experiment.task,
                        training_run_id=protocol.experiment.id,
                        dataset_id=dataset_identity,
                        dataset_hash=table.dataset_hash,
                        feature_schema_id=table.schema_hash,
                        metrics=metrics[model.id],
                        framework="research-os.declarative-experiment",
                        framework_version="v1",
                        model_file=artifact_path,
                        model_family=model.adapter,
                        model_adapter=model.adapter,
                        adapter_version="research-os.declarative-experiment.v1",
                        target=protocol.dataset.target,
                        hyperparameters=dict(model.config),
                        split_strategy=protocol.split.strategy,
                        train_count=len(split.train_indices),
                        test_count=len(split.test_indices),
                        seed=protocol.experiment.seed,
                        implementation_identity=environment["engine"]["sha256"],
                        environment_identity=environment_identity,
                        metadata={"declarative_model_id": model.id},
                    )
                    record = model_registry.register(
                        model_manifest,
                        lineage={
                            "source_run_id": protocol.experiment.id,
                            "protocol_hash": protocol_hash,
                            "dataset_id": dataset_identity,
                            "split_membership_hash": split.membership_hash,
                        },
                        provenance={
                            "dataset": {"id": dataset_identity, "sha256": table.dataset_hash, "schema_id": table.schema_hash},
                            "source_run": {"run_id": protocol.experiment.id, "manifest_path": str((target / "manifest.json").resolve())},
                            "implementation_identity": environment["engine"]["sha256"],
                            "environment_identity": environment_identity,
                        },
                    )
                    model_registry_refs[model.id] = {
                        "record_id": record.record_id,
                        "scientific_model_id": record.scientific_model_id,
                        "artifact_sha256": record.artifact_sha256,
                        "artifact_id": record.manifest.artifact_id,
                    }

        manifest = {
            "protocol": protocol.protocol,
            "experiment_id": protocol.experiment.id,
            "task": protocol.experiment.task,
            "seed": protocol.experiment.seed,
            "created_at": created_at,
            "status": "PASS",
            "dataset": {
                "adapter": protocol.dataset.adapter,
                "row_count": table.row_count,
                "sha256": table.dataset_hash,
                "schema_hash": table.schema_hash,
            },
            "split": {
                "strategy": protocol.split.strategy,
                "train_fraction": protocol.split.train_fraction,
                "train_rows": len(split.train_indices),
                "test_rows": len(split.test_indices),
                "membership_hash": split.membership_hash,
            },
            "models": {
                model.id: {
                    "adapter": model.adapter,
                    "config": dict(model.config),
                    "identity": model_identities[model.id],
                    "fitted_parameters": fitted_parameters[model.id],
                }
                for model in protocol.models
            },
            "protocol_hash": protocol_hash,
            "scientific_protocol_hash": scientific_protocol_hash,
            "compatibility_hash": compatibility_hash,
            "scientific_result_hash": scientific_result_hash,
            "execution_hash": execution_hash,
            "implementation_hash": environment["engine"]["sha256"],
        }
        if model_registry_root is not None:
            manifest["model_registry"] = {
                "registry_root": str(model_registry_root),
                "models": model_registry_refs,
            }
        provenance = {
            "dataset": {
                "declared_path": protocol.dataset.path,
                "resolved_path": table.source_path,
                "sha256": table.dataset_hash,
                "schema_hash": table.schema_hash,
                "row_count": table.row_count,
            },
            "split": {
                "train_row_ids": [table.row_ids[index] for index in split.train_indices],
                "test_row_ids": [table.row_ids[index] for index in split.test_indices],
                "membership_hash": split.membership_hash,
            },
            "compatibility": compatibility_payload,
            "implementation": environment["engine"],
        }
        if model_registry_root is not None:
            provenance["models"] = model_registry_refs
        evidence = {
            "status": "PASS",
            "gates": [
                {"rule_id": "DECL-PROTOCOL-HASH", "status": "PASS", "reason": "protocol hash recorded"},
                {"rule_id": "DECL-DATASET-HASH", "status": "PASS", "reason": "dataset content hash recorded"},
                {"rule_id": "DECL-SPLIT-DETERMINISTIC", "status": "PASS", "reason": "seeded split membership hash recorded"},
                {"rule_id": "DECL-FINITE-METRICS", "status": "PASS", "reason": "all declared metrics are finite"},
                {"rule_id": "DECL-IMPLEMENTATION-ID", "status": "PASS", "reason": "engine source identity recorded"},
            ],
        }
        if model_registry_root is not None:
            evidence["gates"].append({"rule_id": "DECL-MODEL-REGISTRY", "status": "PASS", "reason": "model artifacts were explicitly registered with durable provenance"})

        _write_json(target / "manifest.json", manifest)
        (target / "protocol.yaml").write_text(yaml.safe_dump(protocol_payload, sort_keys=True, allow_unicode=True), encoding="utf-8")
        _write_json(target / "metrics.json", metrics)
        _write_json(target / "provenance.json", provenance)
        _write_json(target / "evidence.json", evidence)
        _write_json(target / "environment.json", environment)
        (target / "report.md").write_text(_report(manifest, metrics), encoding="utf-8")
        if model_registry_root is not None:
            _write_json(target / "model-registry.json", {
                "schema_version": "research-os.experiment-model-registry.v1",
                "registry_root": str(model_registry_root),
                "models": model_registry_refs,
            })

        artifact_hashes = {
            name: sha256_file(target / name)
            for name in (*REQUIRED_ARTIFACTS, *OPTIONAL_ARTIFACTS)
            if name != "hashes.json"
            and (target / name).is_file()
        }
        package_hash = sha256_json({
            "artifacts": artifact_hashes,
            "scientific_result_hash": scientific_result_hash,
            "execution_hash": execution_hash,
        })
        _write_json(target / "hashes.json", {
            "artifacts": artifact_hashes,
            "protocol_hash": protocol_hash,
            "scientific_protocol_hash": scientific_protocol_hash,
            "dataset_hash": table.dataset_hash,
            "dataset_schema_hash": table.schema_hash,
            "split_membership_hash": split.membership_hash,
            "compatibility_hash": compatibility_hash,
            "scientific_result_hash": scientific_result_hash,
            "execution_hash": execution_hash,
            "implementation_hash": environment["engine"]["sha256"],
            "package_hash": package_hash,
        })
        return ExperimentRunResult(str(target), protocol.experiment.id, scientific_result_hash, execution_hash, compatibility_hash, metrics)


def verify_experiment_run(root: str | Path) -> VerificationResult:
    target = Path(root)
    gates: list[dict[str, Any]] = []
    if not target.is_dir():
        raise ExperimentExecutionError(f"experiment run directory does not exist: {target}")
    missing = [name for name in REQUIRED_ARTIFACTS if not (target / name).is_file()]
    if missing:
        raise ExperimentExecutionError(f"experiment run is missing required artifacts: {', '.join(missing)}")

    hashes = _read_json(target / "hashes.json")
    if not isinstance(hashes, Mapping) or not isinstance(hashes.get("artifacts"), Mapping):
        raise ExperimentExecutionError("hashes.json has an invalid structure")
    artifact_names = (*REQUIRED_ARTIFACTS, *(name for name in OPTIONAL_ARTIFACTS if (target / name).is_file()))
    for name in artifact_names:
        if name == "hashes.json":
            continue
        expected = hashes["artifacts"].get(name)
        actual = sha256_file(target / name)
        if expected != actual:
            raise ExperimentExecutionError(f"artifact integrity mismatch: {name}")
    gates.append({"rule_id": "DECL-ARTIFACT-INTEGRITY", "status": "PASS", "reason": "all package artifact hashes match"})

    protocol = load_protocol(target / "protocol.yaml")
    protocol_hash = sha256_json(protocol.to_dict())
    if protocol_hash != hashes.get("protocol_hash"):
        raise ExperimentExecutionError("protocol hash mismatch")
    scientific_protocol_hash = sha256_json(_scientific_protocol_payload(protocol))
    if scientific_protocol_hash != hashes.get("scientific_protocol_hash"):
        raise ExperimentExecutionError("scientific protocol hash mismatch")

    manifest = _read_json(target / "manifest.json")
    metrics = _read_json(target / "metrics.json")
    provenance = _read_json(target / "provenance.json")
    environment = _read_json(target / "environment.json")
    evidence = _read_json(target / "evidence.json")
    if evidence.get("status") != "PASS" or any(gate.get("status") != "PASS" for gate in evidence.get("gates", [])):
        raise ExperimentExecutionError("evidence contains a non-PASS gate")

    compatibility_hash = sha256_json(_compatibility_payload(protocol))
    if compatibility_hash != hashes.get("compatibility_hash") or compatibility_hash != manifest.get("compatibility_hash"):
        raise ExperimentExecutionError("compatibility hash mismatch")
    if scientific_protocol_hash != manifest.get("scientific_protocol_hash"):
        raise ExperimentExecutionError("manifest scientific protocol hash mismatch")

    dataset = manifest.get("dataset", {})
    split = manifest.get("split", {})
    models = manifest.get("models", {})
    model_identities = {model_id: model.get("identity") for model_id, model in models.items()}
    scientific_payload = _scientific_payload(
        scientific_protocol_hash=scientific_protocol_hash,
        dataset_hash=dataset.get("sha256"),
        schema_hash=dataset.get("schema_hash"),
        split_hash=split.get("membership_hash"),
        model_identities=model_identities,
        metrics=metrics,
    )
    scientific_result_hash = sha256_json(scientific_payload)
    if scientific_result_hash != hashes.get("scientific_result_hash") or scientific_result_hash != manifest.get("scientific_result_hash"):
        raise ExperimentExecutionError("scientific result hash mismatch")
    if provenance.get("dataset", {}).get("sha256") != dataset.get("sha256") or provenance.get("split", {}).get("membership_hash") != split.get("membership_hash"):
        raise ExperimentExecutionError("provenance does not match manifest identities")

    recorded_implementation = environment.get("engine", {}).get("sha256")
    if not isinstance(recorded_implementation, str) or len(recorded_implementation) != 64:
        raise ExperimentExecutionError("environment is missing a valid implementation identity")
    if recorded_implementation != manifest.get("implementation_hash") or recorded_implementation != hashes.get("implementation_hash"):
        raise ExperimentExecutionError("implementation identity mismatch")
    if provenance.get("implementation", {}).get("sha256") != recorded_implementation:
        raise ExperimentExecutionError("provenance implementation identity mismatch")

    model_registry_payload = manifest.get("model_registry")
    if model_registry_payload is not None:
        if not isinstance(model_registry_payload, Mapping):
            raise ExperimentExecutionError("model registry metadata is invalid")
        registry_reference_file = target / "model-registry.json"
        if not registry_reference_file.is_file():
            raise ExperimentExecutionError("model registry reference artifact is missing")
        registry_reference = _read_json(registry_reference_file)
        if registry_reference.get("registry_root") != model_registry_payload.get("registry_root") or registry_reference.get("models") != model_registry_payload.get("models"):
            raise ExperimentExecutionError("model registry reference artifact does not match manifest")
        registry_root = model_registry_payload.get("registry_root")
        models_payload = model_registry_payload.get("models")
        if not isinstance(registry_root, str) or not isinstance(models_payload, Mapping):
            raise ExperimentExecutionError("model registry metadata is incomplete")
        registry = ModelRegistry(root=registry_root)
        for model_id, reference in models_payload.items():
            if not isinstance(reference, Mapping):
                raise ExperimentExecutionError(f"model registry reference is invalid: {model_id}")
            try:
                verification = registry.verify(str(reference["record_id"]))
            except (KeyError, ValueError, OSError) as exc:
                raise ExperimentExecutionError(f"model registry verification failed: {model_id}") from exc
            if verification.status != "PASS":
                raise ExperimentExecutionError(f"model registry verification failed: {model_id}: {verification.first_loss}")
            if verification.artifact_sha256 != reference.get("artifact_sha256"):
                raise ExperimentExecutionError(f"model registry artifact identity mismatch: {model_id}")
        gates.append({"rule_id": "DECL-MODEL-REGISTRY", "status": "PASS", "reason": "registered model records and artifact bytes verify"})

    execution_hash = sha256_json({"scientific_result_hash": scientific_result_hash, "environment": environment})
    if execution_hash != hashes.get("execution_hash") or execution_hash != manifest.get("execution_hash"):
        raise ExperimentExecutionError("execution hash mismatch")
    package_hash = sha256_json({
        "artifacts": dict(hashes["artifacts"]),
        "scientific_result_hash": scientific_result_hash,
        "execution_hash": execution_hash,
    })
    if package_hash != hashes.get("package_hash"):
        raise ExperimentExecutionError("package hash mismatch")
    gates.extend([
        {"rule_id": "DECL-PROTOCOL-IDENTITY", "status": "PASS", "reason": "protocol and compatibility identities reproduce"},
        {"rule_id": "DECL-SCIENTIFIC-IDENTITY", "status": "PASS", "reason": "scientific result identity reproduces"},
        {"rule_id": "DECL-IMPLEMENTATION-IDENTITY", "status": "PASS", "reason": "recorded implementation identity is internally consistent"},
        {"rule_id": "DECL-EXECUTION-IDENTITY", "status": "PASS", "reason": "execution identity reproduces"},
    ])
    return VerificationResult("PASS", str(target), scientific_result_hash, execution_hash, tuple(gates))


def inspect_experiment_run(root: str | Path) -> dict[str, Any]:
    verification = verify_experiment_run(root)
    target = Path(root)
    manifest = _read_json(target / "manifest.json")
    metrics = _read_json(target / "metrics.json")
    return {
        "verification": verification.to_dict(),
        "experiment_id": manifest["experiment_id"],
        "task": manifest["task"],
        "dataset": manifest["dataset"],
        "split": manifest["split"],
        "models": {key: {"adapter": value["adapter"], "identity": value["identity"]} for key, value in manifest["models"].items()},
        "metrics": metrics,
        "model_registry": manifest.get("model_registry"),
        "scientific_protocol_hash": manifest["scientific_protocol_hash"],
        "scientific_result_hash": manifest["scientific_result_hash"],
        "execution_hash": manifest["execution_hash"],
        "implementation_hash": manifest["implementation_hash"],
    }


def reproduce_experiment_run(
    source_root: str | Path,
    output_root: str | Path = "reproduced-runs",
    *,
    registry: ExperimentRegistry | None = None,
) -> ExperimentReproductionResult:
    """Re-execute a verified run with its exact scientific identities.

    The run package does not embed a second copy of the dataset. Reproduction
    therefore resolves the recorded provenance path and verifies its bytes
    before execution. Any missing dependency, implementation drift, or
    scientific identity mismatch fails closed.
    """
    source = Path(source_root).resolve()
    verify_experiment_run(source)
    source_manifest = _read_json(source / "manifest.json")
    provenance = _read_json(source / "provenance.json")
    source_environment = _read_json(source / "environment.json")
    source_implementation = source_environment.get("engine", {}).get("sha256")
    try:
        current_implementation = _implementation_identity()["sha256"]
    except OSError as exc:
        raise ExperimentExecutionError("reproduction blocked: implementation artifact unavailable") from exc
    if source_implementation != current_implementation:
        raise ExperimentExecutionError("reproduction blocked: implementation identity differs from source run")

    dataset_record = provenance.get("dataset", {})
    dataset_path_value = dataset_record.get("resolved_path")
    expected_dataset_hash = source_manifest.get("dataset", {}).get("sha256")
    if not isinstance(dataset_path_value, str) or not dataset_path_value.strip():
        raise ExperimentExecutionError("reproduction blocked: source run has no resolved dataset dependency")
    dataset_path = Path(dataset_path_value)
    if not dataset_path.is_file():
        raise ExperimentExecutionError(f"reproduction blocked: dataset dependency is unavailable: {dataset_path}")
    if sha256_file(dataset_path) != expected_dataset_hash or dataset_record.get("sha256") != expected_dataset_hash:
        raise ExperimentExecutionError("reproduction blocked: dataset content hash changed")

    source_protocol = load_protocol(source / "protocol.yaml")
    protocol_payload = source_protocol.to_dict()
    protocol_payload["dataset"]["path"] = str(dataset_path)
    if isinstance(protocol_payload.get("model_registry"), Mapping) and protocol_payload["model_registry"].get("enabled"):
        # Registry location is operational metadata. Reproduction gets its
        # own durable namespace and cannot overwrite the source records.
        protocol_payload["model_registry"] = {
            **protocol_payload["model_registry"],
            "root": str((Path(output_root).resolve() / "model-registry")),
        }
    engine = ExperimentEngine(registry=registry)
    with tempfile.TemporaryDirectory(prefix="research-os-experiment-reproduce-") as temporary:
        protocol_path = Path(temporary) / "protocol.yaml"
        protocol_path.write_text(yaml.safe_dump(protocol_payload, sort_keys=True, allow_unicode=True), encoding="utf-8")
        reproduced = engine.run(protocol_path, output_root)

    verify_experiment_run(reproduced.root)
    reproduced_manifest = _read_json(Path(reproduced.root) / "manifest.json")
    for field in ("scientific_protocol_hash", "compatibility_hash", "implementation_hash"):
        if source_manifest.get(field) != reproduced_manifest.get(field):
            raise ExperimentExecutionError(f"reproduction identity mismatch: {field}")
    if source_manifest.get("dataset", {}).get("sha256") != reproduced_manifest.get("dataset", {}).get("sha256"):
        raise ExperimentExecutionError("reproduction identity mismatch: dataset hash")
    if source_manifest.get("split", {}).get("membership_hash") != reproduced_manifest.get("split", {}).get("membership_hash"):
        raise ExperimentExecutionError("reproduction identity mismatch: split membership")
    if source_manifest.get("scientific_result_hash") != reproduced_manifest.get("scientific_result_hash"):
        raise ExperimentExecutionError("reproduction scientific identity mismatch")
    return ExperimentReproductionResult(
        source_root=str(source),
        reproduced_root=str(Path(reproduced.root).resolve()),
        source_scientific_result_hash=str(source_manifest["scientific_result_hash"]),
        scientific_result_hash=str(reproduced_manifest["scientific_result_hash"]),
        compatibility_hash=str(reproduced_manifest["compatibility_hash"]),
        implementation_hash=str(reproduced_manifest["implementation_hash"]),
    )


def compare_experiment_runs(left: str | Path, right: str | Path) -> dict[str, Any]:
    verify_experiment_run(left)
    verify_experiment_run(right)
    left_root, right_root = Path(left), Path(right)
    left_manifest = _read_json(left_root / "manifest.json")
    right_manifest = _read_json(right_root / "manifest.json")
    if left_manifest.get("compatibility_hash") != right_manifest.get("compatibility_hash"):
        raise ExperimentExecutionError("experiment runs are methodologically incompatible")
    left_metrics = _read_json(left_root / "metrics.json")
    right_metrics = _read_json(right_root / "metrics.json")
    deltas = {
        model_id: {
            metric_id: float(right_metrics[model_id][metric_id]) - float(left_metrics[model_id][metric_id])
            for metric_id in left_metrics[model_id]
        }
        for model_id in left_metrics
    }
    left_models = left_manifest.get("model_registry", {}).get("models", {}) if isinstance(left_manifest.get("model_registry"), Mapping) else {}
    right_models = right_manifest.get("model_registry", {}).get("models", {}) if isinstance(right_manifest.get("model_registry"), Mapping) else {}
    return {
        "compatible": True,
        "compatibility_hash": left_manifest["compatibility_hash"],
        "same_dataset_content": left_manifest["dataset"]["sha256"] == right_manifest["dataset"]["sha256"],
        "same_implementation": left_manifest.get("implementation_hash") == right_manifest.get("implementation_hash"),
        "same_scientific_result": left_manifest["scientific_result_hash"] == right_manifest["scientific_result_hash"],
        "model_registry": {
            "present_in_both": bool(left_models) and bool(right_models),
            "same_scientific_models": {
                model_id: left_models[model_id].get("scientific_model_id") == right_models.get(model_id, {}).get("scientific_model_id")
                for model_id in left_models
                if model_id in right_models
            },
            "same_artifacts": {
                model_id: left_models[model_id].get("artifact_sha256") == right_models.get(model_id, {}).get("artifact_sha256")
                for model_id in left_models
                if model_id in right_models
            },
        },
        "metric_deltas_right_minus_left": deltas,
    }
