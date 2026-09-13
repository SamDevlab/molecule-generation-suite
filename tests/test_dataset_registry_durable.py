from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research_os.cli import main
from research_os.datasets import DatasetManifest, DatasetRegistry, DatasetRegistryError
from research_os.experiments import ExperimentEngine, reproduce_experiment_run, verify_experiment_run


def _csv(path: Path, text: str = "x,y\n1,2\n2,4\n3,6\n") -> Path:
    path.write_text(text, encoding="utf-8", newline="")
    return path


def test_managed_registration_survives_source_deletion_and_restart(tmp_path: Path) -> None:
    source = _csv(tmp_path / "source.csv")
    root = tmp_path / "registry"
    first = DatasetRegistry(root=root)
    manifest = first.register_file(dataset_id="fixture", version="v1", schema_id="csv-v1", path=source)
    record = first.get_record("fixture", "v1")
    assert record.record_id and record.scientific_dataset_id == manifest.scientific_dataset_id
    assert Path(manifest.artifact_path).is_relative_to(root / "artifacts")
    source.unlink()

    restarted = DatasetRegistry(root=root)
    verification = restarted.verify("fixture", "v1")
    assert verification.status == "PASS"
    assert restarted.get("fixture", "v1").sha256 == manifest.sha256


def test_identity_separates_scientific_and_artifact_metadata(tmp_path: Path) -> None:
    source = _csv(tmp_path / "a.csv")
    first = DatasetRegistry(root=tmp_path / "one").register_file(dataset_id="fixture", version="v1", schema_id="csv-v1", path=source)
    second = DatasetManifest.from_mapping({**first.to_dict(), "created_at": "2099-01-01T00:00:00+00:00", "artifact_path": str(tmp_path / "elsewhere.csv")})
    assert first.scientific_dataset_id == second.scientific_dataset_id
    assert first.artifact_id == second.artifact_id
    implementation_changed = DatasetManifest.from_mapping({**first.to_dict(), "implementation_identity": "f" * 64})
    assert implementation_changed.scientific_dataset_id == first.scientific_dataset_id
    changed = DatasetManifest.from_mapping({**first.to_dict(), "target": "different"})
    assert changed.scientific_dataset_id != first.scientific_dataset_id


def test_artifact_tampering_and_deletion_fail_closed(tmp_path: Path) -> None:
    source = _csv(tmp_path / "source.csv")
    registry = DatasetRegistry(root=tmp_path / "registry")
    manifest = registry.register_file(dataset_id="fixture", version="v1", schema_id="csv-v1", path=source)
    artifact = Path(manifest.artifact_path)
    artifact.write_bytes(b"tampered")
    assert registry.verify("fixture", "v1").first_loss == "DATASET_ARTIFACT_HASH_MISMATCH"
    artifact.unlink()
    assert registry.verify("fixture", "v1").first_loss == "DATASET_ARTIFACT_MISSING"


def test_external_reference_is_never_copied_and_unavailable_is_indeterminate(tmp_path: Path) -> None:
    source = _csv(tmp_path / "external.csv")
    root = tmp_path / "registry"
    registry = DatasetRegistry(root=root)
    manifest = registry.register_file(dataset_id="external", version="v1", schema_id="csv-v1", path=source, artifact_mode="external")
    assert not (root / "artifacts" / "sha256").exists() or not list((root / "artifacts" / "sha256").rglob("*"))
    source.unlink()
    result = registry.verify("external", "v1")
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.first_loss == "SOURCE_ARTIFACT_UNAVAILABLE"
    assert manifest.storage_format == "external-reference"


def test_registration_is_idempotent_but_conflicts_are_rejected(tmp_path: Path) -> None:
    source = _csv(tmp_path / "source.csv")
    registry = DatasetRegistry(root=tmp_path / "registry")
    first = registry.register_file(dataset_id="fixture", version="v1", schema_id="csv-v1", path=source)
    assert registry.register_file(dataset_id="fixture", version="v1", schema_id="csv-v1", path=source).sha256 == first.sha256
    other = _csv(tmp_path / "other.csv", "x,y\n1,3\n2,5\n3,7\n")
    with pytest.raises(DatasetRegistryError, match="conflicting dataset registration"):
        registry.register_file(dataset_id="fixture", version="v1", schema_id="csv-v1", path=other)


def test_atomic_manifest_failure_does_not_index_a_partial_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _csv(tmp_path / "source.csv")
    registry = DatasetRegistry(root=tmp_path / "registry")

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("simulated interrupted write")

    monkeypatch.setattr(registry, "_atomic_write_json", fail)
    with pytest.raises(OSError, match="interrupted"):
        registry.register_file(dataset_id="fixture", version="v1", schema_id="csv-v1", path=source)
    with pytest.raises(KeyError):
        registry.get("fixture", "v1")


def test_path_traversal_and_restricted_copy_fail_closed(tmp_path: Path) -> None:
    source = _csv(tmp_path / "source.csv")
    registry = DatasetRegistry(root=tmp_path / "registry")
    with pytest.raises(DatasetRegistryError, match="safe registry references"):
        registry.register_file(dataset_id="../escape", version="v1", schema_id="csv-v1", path=source)
    with pytest.raises(DatasetRegistryError, match="explicit external mode"):
        registry.register_file(dataset_id="restricted", version="v1", schema_id="csv-v1", path=source, redistribution_status="restricted")


def test_records_are_content_addressed_and_durable(tmp_path: Path) -> None:
    registry = DatasetRegistry(root=tmp_path / "registry")
    manifest = registry.register_records(dataset_id="records", version="v1", schema_id="records-v1", records=[{"x": 1}, {"x": 2}])
    assert registry.verify("records", "v1").status == "PASS"
    assert DatasetRegistry(root=tmp_path / "registry").verify("records", "v1").status == "PASS"
    assert Path(manifest.artifact_path).read_text(encoding="utf-8") == '[{"x":1},{"x":2}]'


def test_lineage_requires_available_parent_and_is_preserved(tmp_path: Path) -> None:
    registry = DatasetRegistry(root=tmp_path / "registry")
    parent = registry.register_records(dataset_id="parent", version="v1", schema_id="s", records=[{"x": 1}])
    child = registry.register_records(dataset_id="child", version="v1", schema_id="s", records=[{"x": 1}], parent_datasets=(f"{parent.dataset_id}@{parent.version}",))
    assert registry.verify("child", "v1").status == "PASS"
    assert registry.get_record("child", "v1").lineage["parent_datasets"] == ["parent@v1"]
    with pytest.raises(DatasetRegistryError, match="DATASET_PARENT_MISSING"):
        registry.register_records(dataset_id="orphan", version="v1", schema_id="s", records=[{"x": 1}], parent_datasets=("missing@v1",))


def test_corrupt_persisted_record_is_not_accepted(tmp_path: Path) -> None:
    source = _csv(tmp_path / "source.csv")
    root = tmp_path / "registry"
    registry = DatasetRegistry(root=root)
    registry.register_file(dataset_id="fixture", version="v1", schema_id="csv-v1", path=source)
    record_path = next((root / "manifests").glob("*.manifest.json"))
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    payload["record_hash"] = "0" * 64
    record_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DatasetRegistryError, match="identity mismatch"):
        DatasetRegistry(root=root)


def test_unsupported_record_schema_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "registry"
    (root / "manifests").mkdir(parents=True)
    (root / "manifests" / "unknown.manifest.json").write_text(json.dumps({"schema_version": "research-os.dataset-record.v9"}), encoding="utf-8")
    with pytest.raises(DatasetRegistryError, match="unsupported dataset record schema"):
        DatasetRegistry(root=root)


def test_registry_cli_verify_inspect_and_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _csv(tmp_path / "source.csv")
    manifest = DatasetManifest.from_file(dataset_id="fixture", version="v1", schema_id="csv-v1", path=str(source), row_count=3, column_count=2)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest.to_dict()), encoding="utf-8")
    root = tmp_path / "registry"
    assert main(["registry", "dataset", "register", str(manifest_path), "--root", str(root)]) == 0
    assert main(["registry", "dataset", "verify", "fixture", "v1", "--root", str(root)]) == 0
    assert main(["registry", "dataset", "inspect", "fixture", "v1", "--root", str(root)]) == 0
    assert main(["registry", "dataset", "list", "--root", str(root)]) == 0
    assert "PASS" in capsys.readouterr().out


def test_declarative_engine_consumes_dataset_registry_and_reproduction_reverifies_it(tmp_path: Path) -> None:
    source = _csv(tmp_path / "source.csv", "x,y\n" + "".join(f"{index},{2 * index}\n" for index in range(1, 21)))
    dataset_root = tmp_path / "datasets"
    dataset = DatasetRegistry(root=dataset_root).register_file(dataset_id="training", version="v1", schema_id="csv-v1", path=source)
    protocol = {
        "protocol": "research-os.declarative-experiment.v1",
        "experiment": {"id": "DATASET-REGISTRY-001", "task": "regression", "seed": 42},
        "dataset": {"adapter": "csv", "path": "ignored.csv", "target": "y", "features": ["x"]},
        "dataset_registry": {"enabled": True, "root": str(dataset_root), "dataset_id": "training", "version": "v1"},
        "split": {"strategy": "random", "train_fraction": 0.8},
        "models": [{"id": "ols", "adapter": "linear_regression"}],
        "metrics": ["mae", "rmse", "r2"],
        "evidence": {"require_dataset_hash": True, "require_protocol_hash": True, "fail_closed": True},
    }
    protocol_path = tmp_path / "protocol.yaml"
    protocol_path.write_text(yaml.safe_dump(protocol, sort_keys=False), encoding="utf-8")
    result = ExperimentEngine().run(protocol_path, tmp_path / "runs")
    manifest = json.loads((Path(result.root) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset"]["registry"]["scientific_dataset_id"] == dataset.scientific_dataset_id
    assert verify_experiment_run(result.root).status == "PASS"
    reproduced = reproduce_experiment_run(result.root, tmp_path / "reproduced")
    assert verify_experiment_run(reproduced.reproduced_root).status == "PASS"

    artifact = Path(dataset.artifact_path)
    artifact.write_bytes(b"mutated")
    with pytest.raises(Exception, match="dataset registry verification failed"):
        verify_experiment_run(result.root)
