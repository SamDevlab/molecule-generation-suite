from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any, Mapping

import yaml

from research_os.core.hashing import sha256_file, sha256_json
from research_os.experiments.registry import ExperimentExecutionError, ExperimentRegistry
from research_os.experiments.schema import PROTOCOL_ID, ExperimentProtocol, load_protocol


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

        _write_json(target / "manifest.json", manifest)
        (target / "protocol.yaml").write_text(yaml.safe_dump(protocol_payload, sort_keys=True, allow_unicode=True), encoding="utf-8")
        _write_json(target / "metrics.json", metrics)
        _write_json(target / "provenance.json", provenance)
        _write_json(target / "evidence.json", evidence)
        _write_json(target / "environment.json", environment)
        (target / "report.md").write_text(_report(manifest, metrics), encoding="utf-8")

        artifact_hashes = {
            name: sha256_file(target / name)
            for name in REQUIRED_ARTIFACTS
            if name != "hashes.json"
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
    for name in REQUIRED_ARTIFACTS:
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
        "scientific_protocol_hash": manifest["scientific_protocol_hash"],
        "scientific_result_hash": manifest["scientific_result_hash"],
        "execution_hash": manifest["execution_hash"],
        "implementation_hash": manifest["implementation_hash"],
    }


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
    return {
        "compatible": True,
        "compatibility_hash": left_manifest["compatibility_hash"],
        "same_dataset_content": left_manifest["dataset"]["sha256"] == right_manifest["dataset"]["sha256"],
        "same_implementation": left_manifest.get("implementation_hash") == right_manifest.get("implementation_hash"),
        "same_scientific_result": left_manifest["scientific_result_hash"] == right_manifest["scientific_result_hash"],
        "metric_deltas_right_minus_left": deltas,
    }
