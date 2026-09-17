from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research_os.artifacts import ModelArtifactManifest
from research_os.cli import main
from research_os.datasets import DatasetRegistry
from research_os.experiments import ExperimentEngine, compare_experiment_runs, reproduce_experiment_run, verify_experiment_run
from research_os.ml.registry import ModelRegistry, ModelRegistryError


def _manifest(path: Path, *, dataset_id: str = "DS-1", dataset_hash: str = "a" * 64) -> ModelArtifactManifest:
    return ModelArtifactManifest.from_model_file(
        model_id="model-001",
        task="regression",
        training_run_id="RUN-001",
        dataset_id=dataset_id,
        dataset_hash=dataset_hash,
        feature_schema_id="features-v1",
        metrics={"mae": 0.25, "rmse": 0.5},
        framework="fixture-regressor",
        framework_version="1.0",
        model_file=path,
        model_family="fixture-regressor",
        model_adapter="fixture-regressor",
        adapter_version="1.0",
        preprocessing_identity="prep-v1",
        target="y",
        hyperparameters={"alpha": 1.0},
        dataset_version="v1",
        implementation_identity="b" * 64,
        environment_identity="c" * 64,
        split_strategy="random",
        train_count=8,
        validation_count=1,
        test_count=1,
        seed=42,
    )


def test_register_get_survives_process_restart_and_verifies_without_deserialization(tmp_path: Path) -> None:
    source = tmp_path / "model.bin"
    source.write_bytes(b"opaque model bytes; not a pickle")
    root = tmp_path / "registry"
    manifest = _manifest(source)
    registry = ModelRegistry(root=root)
    record = registry.register(manifest, provenance={"implementation_identity": "b" * 64})
    assert registry.verify(record.record_id).status == "PASS"

    restarted = ModelRegistry(root=root)
    loaded = restarted.get(record.record_id)
    assert loaded.scientific_model_id == manifest.scientific_model_id
    assert loaded.artifact_sha256 == manifest.artifact_sha256
    assert restarted.verify(record.record_id).status == "PASS"
    assert (root / "records" / f"{record.record_id}.json").is_file()
    assert list((root / "artifacts" / "sha256").rglob(manifest.model_hash or ""))


def test_registration_is_idempotent_but_conflicting_artifact_is_fail_closed(tmp_path: Path) -> None:
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    registry = ModelRegistry(root=tmp_path / "registry")
    registered = registry.register(_manifest(first))
    assert registry.register(_manifest(first)).record_id == registered.record_id
    with pytest.raises(ModelRegistryError, match="conflicting model registration"):
        registry.register(_manifest(second))


def test_record_path_traversal_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "model.bin"
    source.write_bytes(b"model")
    with pytest.raises(ModelRegistryError, match="unsafe model record id"):
        ModelRegistry(root=tmp_path / "registry").register(_manifest(source), record_id="../outside")


def test_scientific_identity_is_metadata_and_path_neutral_but_scientific_mutation_changes_it(tmp_path: Path) -> None:
    first = tmp_path / "a" / "model.bin"
    second = tmp_path / "b" / "model.bin"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"same")
    second.write_bytes(b"same")
    left = _manifest(first)
    right = _manifest(second)
    assert left.scientific_model_id == right.scientific_model_id
    assert left.artifact_sha256 == right.artifact_sha256
    assert left.manifest_hash != right.manifest_hash
    assert _manifest(first, dataset_id="DS-2").scientific_model_id != left.scientific_model_id


def test_artifact_tampering_missing_bytes_and_record_tampering_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "model.bin"
    source.write_bytes(b"original")
    root = tmp_path / "registry"
    registry = ModelRegistry(root=root)
    record = registry.register(_manifest(source))
    artifact = root / "artifacts" / "sha256" / (record.artifact_sha256 or "")[:2] / (record.artifact_sha256 or "")
    artifact.write_bytes(b"tampered")
    assert registry.verify(record.record_id).first_loss == "MODEL_ARTIFACT_HASH_MISMATCH"
    artifact.unlink()
    assert registry.verify(record.record_id).first_loss == "MODEL_ARTIFACT_MISSING"

    # Recreate a clean registry, then mutate its persisted record without
    # reloading the process to exercise revalidation at the verification gate.
    source.write_bytes(b"original")
    clean_root = tmp_path / "clean-registry"
    clean = ModelRegistry(root=clean_root)
    clean_record = clean.register(_manifest(source))
    record_path = clean_root / "records" / f"{clean_record.record_id}.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    payload["manifest"]["task"] = "mutated"
    record_path.write_text(json.dumps(payload), encoding="utf-8")
    assert clean.verify(clean_record.record_id).first_loss == "MODEL_RECORD_HASH_MISMATCH"


def test_dataset_reference_and_implementation_provenance_are_checked(tmp_path: Path) -> None:
    dataset_registry = DatasetRegistry(root=tmp_path / "datasets")
    dataset = dataset_registry.register_records(dataset_id="DS-1", version="v1", schema_id="features-v1", records=[{"x": 1}, {"x": 2}])
    source = tmp_path / "model.bin"
    source.write_bytes(b"model")
    manifest = _manifest(source, dataset_id=dataset.dataset_id, dataset_hash=dataset.sha256)
    registry = ModelRegistry(root=tmp_path / "models", dataset_registry=dataset_registry)
    record = registry.register(manifest, provenance={"implementation_identity": "b" * 64})
    assert registry.verify(record.record_id).status == "PASS"

    changed = DatasetRegistry(manifests=[])
    changed.register_records(dataset_id="DS-1", version="v1", schema_id="features-v1", records=[{"x": 99}])
    assert ModelRegistry(root=tmp_path / "models", dataset_registry=changed).verify(record.record_id).first_loss == "DATASET_IDENTITY_MISMATCH"


def test_registry_cli_register_verify_inspect_and_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "model.bin"
    source.write_bytes(b"cli model")
    manifest = _manifest(source)
    manifest_path = tmp_path / "manifest.json"
    manifest.write(manifest_path)
    root = tmp_path / "registry"
    assert main(["registry", "model", "register", str(manifest_path), "--root", str(root)]) == 0
    registered = json.loads(capsys.readouterr().out)
    record_id = registered["record"]["record_id"]
    assert main(["registry", "model", "verify", record_id, "--root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"
    assert main(["registry", "model", "inspect", record_id, "--root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["verification"]["status"] == "PASS"
    assert main(["registry", "model", "list", "--root", str(root)]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1


def _experiment_protocol(path: Path, registry_root: Path) -> Path:
    payload = {
        "protocol": "research-os.declarative-experiment.v1",
        "experiment": {"id": "MODEL-REGISTRY-001", "task": "regression", "seed": 42},
        "dataset": {"adapter": "csv", "path": "data.csv", "target": "y", "features": ["x1", "x2"]},
        "split": {"strategy": "random", "train_fraction": 0.8},
        "models": [{"id": "ols", "adapter": "linear_regression"}],
        "metrics": ["mae", "rmse", "r2"],
        "evidence": {"require_dataset_hash": True, "require_protocol_hash": True, "fail_closed": True},
        "model_registry": {"enabled": True, "root": str(registry_root)},
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_experiment_engine_explicit_registration_integrates_with_verify_and_reproduce(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    rows = ["x1,x2,y"] + [f"{i},{(i * i + 3) % 11},{1.25 + 2 * i - 0.5 * ((i * i + 3) % 11)}" for i in range(20)]
    data.write_text("\n".join(rows) + "\n", encoding="utf-8")
    protocol = _experiment_protocol(tmp_path / "protocol.yaml", tmp_path / "model-registry")
    result = ExperimentEngine().run(protocol, tmp_path / "runs")
    assert verify_experiment_run(result.root).status == "PASS"
    run_manifest = json.loads((Path(result.root) / "manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["model_registry"]["models"]["ols"]["artifact_sha256"]
    assert json.loads((Path(result.root) / "model-registry.json").read_text(encoding="utf-8"))["models"] == run_manifest["model_registry"]["models"]
    reproduced = reproduce_experiment_run(result.root, tmp_path / "reproduced")
    assert reproduced.status == "PASS"
    reproduced_manifest = json.loads((Path(reproduced.reproduced_root) / "manifest.json").read_text(encoding="utf-8"))
    assert reproduced_manifest["model_registry"]["models"]["ols"]["scientific_model_id"] == run_manifest["model_registry"]["models"]["ols"]["scientific_model_id"]
    assert verify_experiment_run(reproduced.reproduced_root).status == "PASS"
    comparison = compare_experiment_runs(result.root, reproduced.reproduced_root)
    assert comparison["model_registry"]["same_scientific_models"]["ols"] is True
