from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research_os.experiments import (
    ExperimentEngine,
    ExperimentExecutionError,
    ProtocolError,
    compare_experiment_runs,
    inspect_experiment_run,
    load_protocol,
    verify_experiment_run,
)
from research_os.experiments.engine import REQUIRED_ARTIFACTS


REFERENCE_PROTOCOL = Path("examples/experiments/reference-regression.yaml")


def _protocol_payload(tmp_path: Path, *, experiment_id: str = "TEST-DECL-001", dataset_name: str = "data.csv") -> dict:
    return {
        "protocol": "research-os.declarative-experiment.v1",
        "experiment": {"id": experiment_id, "task": "regression", "seed": 42},
        "dataset": {"adapter": "csv", "path": dataset_name, "target": "y", "features": ["x1", "x2"]},
        "split": {"strategy": "random", "train_fraction": 0.8},
        "models": [{"id": "ols", "adapter": "linear_regression"}],
        "metrics": ["mae", "rmse", "r2"],
        "evidence": {"require_dataset_hash": True, "require_protocol_hash": True, "fail_closed": True},
    }


def _write_dataset(path: Path, *, offset: float = 0.0) -> None:
    rows = ["x1,x2,y"]
    for index in range(20):
        x1 = float(index)
        x2 = float((index * index + 3) % 11)
        y = 1.25 + 2.0 * x1 - 0.5 * x2 + offset
        rows.append(f"{x1},{x2},{y}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_protocol(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_reference_protocol_is_domain_neutral_and_valid() -> None:
    protocol = load_protocol(REFERENCE_PROTOCOL)
    assert protocol.experiment.task == "regression"
    assert protocol.dataset.adapter == "csv"
    assert protocol.dataset.features == ("x1", "x2")
    rendered = json.dumps(protocol.to_dict()).lower()
    for forbidden in ("solubility", "smiles", "molecule", "rdkit", "cantera"):
        assert forbidden not in rendered


def test_protocol_rejects_unknown_key(tmp_path: Path) -> None:
    _write_dataset(tmp_path / "data.csv")
    payload = _protocol_payload(tmp_path)
    payload["surprise"] = "ignored-by-lenient-parser"
    path = tmp_path / "protocol.yaml"
    _write_protocol(path, payload)
    with pytest.raises(ProtocolError, match="unknown keys"):
        load_protocol(path)


def test_protocol_rejects_unregistered_execution_components(tmp_path: Path) -> None:
    _write_dataset(tmp_path / "data.csv")
    payload = _protocol_payload(tmp_path)
    payload["models"][0]["adapter"] = "arbitrary.python.import"
    path = tmp_path / "protocol.yaml"
    _write_protocol(path, payload)
    with pytest.raises(ExperimentExecutionError, match="unsupported model adapter"):
        ExperimentEngine().run(path, tmp_path / "runs")


def test_json_protocol_is_supported(tmp_path: Path) -> None:
    _write_dataset(tmp_path / "data.csv")
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(_protocol_payload(tmp_path)), encoding="utf-8")
    assert load_protocol(path).protocol == "research-os.declarative-experiment.v1"


def test_reference_run_emits_required_artifacts_and_verifies(tmp_path: Path) -> None:
    result = ExperimentEngine().run(REFERENCE_PROTOCOL, tmp_path)
    root = Path(result.root)
    assert set(REQUIRED_ARTIFACTS) == {path.name for path in root.iterdir() if path.is_file()}
    verification = verify_experiment_run(root)
    assert verification.status == "PASS"
    assert verification.scientific_result_hash == result.scientific_result_hash
    assert set(result.metrics["ordinary_least_squares"]) == {"mae", "rmse", "r2"}
    environment = json.loads((root / "environment.json").read_text(encoding="utf-8"))
    implementation_hash = environment["engine"]["sha256"]
    assert len(implementation_hash) == 64
    assert environment["engine"]["files"]


def test_identical_runs_reproduce_scientific_and_split_hashes(tmp_path: Path) -> None:
    left = ExperimentEngine().run(REFERENCE_PROTOCOL, tmp_path / "left")
    right = ExperimentEngine().run(REFERENCE_PROTOCOL, tmp_path / "right")
    assert left.scientific_result_hash == right.scientific_result_hash
    left_manifest = json.loads((Path(left.root) / "manifest.json").read_text(encoding="utf-8"))
    right_manifest = json.loads((Path(right.root) / "manifest.json").read_text(encoding="utf-8"))
    assert left_manifest["split"]["membership_hash"] == right_manifest["split"]["membership_hash"]
    comparison = compare_experiment_runs(left.root, right.root)
    assert comparison["compatible"] is True
    assert comparison["same_dataset_content"] is True
    assert comparison["same_implementation"] is True
    assert comparison["same_scientific_result"] is True
    assert all(value == pytest.approx(0.0) for values in comparison["metric_deltas_right_minus_left"].values() for value in values.values())


def test_scientific_identity_ignores_experiment_label_and_dataset_location(tmp_path: Path) -> None:
    left_dir = tmp_path / "left-input"
    right_dir = tmp_path / "right-input"
    left_dir.mkdir()
    right_dir.mkdir()
    _write_dataset(left_dir / "data.csv")
    _write_dataset(right_dir / "relocated.csv")

    left_payload = _protocol_payload(left_dir, experiment_id="PORTABLE-A", dataset_name="data.csv")
    right_payload = _protocol_payload(right_dir, experiment_id="PORTABLE-B", dataset_name="relocated.csv")
    left_protocol = left_dir / "protocol.yaml"
    right_protocol = right_dir / "renamed-protocol.yaml"
    _write_protocol(left_protocol, left_payload)
    _write_protocol(right_protocol, right_payload)

    left = ExperimentEngine().run(left_protocol, tmp_path / "left-run")
    right = ExperimentEngine().run(right_protocol, tmp_path / "right-run")
    left_hashes = json.loads((Path(left.root) / "hashes.json").read_text(encoding="utf-8"))
    right_hashes = json.loads((Path(right.root) / "hashes.json").read_text(encoding="utf-8"))

    assert left_hashes["protocol_hash"] != right_hashes["protocol_hash"]
    assert left_hashes["scientific_protocol_hash"] == right_hashes["scientific_protocol_hash"]
    assert left.scientific_result_hash == right.scientific_result_hash
    comparison = compare_experiment_runs(left.root, right.root)
    assert comparison["compatible"] is True
    assert comparison["same_dataset_content"] is True
    assert comparison["same_scientific_result"] is True


def test_tampering_with_hashed_artifact_fails_closed(tmp_path: Path) -> None:
    result = ExperimentEngine().run(REFERENCE_PROTOCOL, tmp_path)
    metrics_path = Path(result.root) / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["ordinary_least_squares"]["rmse"] += 1.0
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")
    with pytest.raises(ExperimentExecutionError, match="artifact integrity mismatch"):
        verify_experiment_run(result.root)


def test_missing_artifact_fails_closed(tmp_path: Path) -> None:
    result = ExperimentEngine().run(REFERENCE_PROTOCOL, tmp_path)
    (Path(result.root) / "evidence.json").unlink()
    with pytest.raises(ExperimentExecutionError, match="missing required artifacts"):
        verify_experiment_run(result.root)


def test_compare_allows_schema_compatible_dataset_content_change(tmp_path: Path) -> None:
    left_dir = tmp_path / "left-input"
    right_dir = tmp_path / "right-input"
    left_dir.mkdir()
    right_dir.mkdir()
    _write_dataset(left_dir / "data.csv", offset=0.0)
    _write_dataset(right_dir / "data.csv", offset=0.125)
    left_protocol = left_dir / "protocol.yaml"
    right_protocol = right_dir / "protocol.yaml"
    _write_protocol(left_protocol, _protocol_payload(left_dir))
    _write_protocol(right_protocol, _protocol_payload(right_dir))
    left = ExperimentEngine().run(left_protocol, tmp_path / "left-run")
    right = ExperimentEngine().run(right_protocol, tmp_path / "right-run")
    comparison = compare_experiment_runs(left.root, right.root)
    assert comparison["compatible"] is True
    assert comparison["same_dataset_content"] is False


def test_compare_rejects_methodologically_incompatible_runs(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _write_dataset(first / "data.csv")
    _write_dataset(second / "data.csv")
    first_payload = _protocol_payload(first)
    second_payload = _protocol_payload(second)
    second_payload["split"]["train_fraction"] = 0.7
    first_protocol = first / "protocol.yaml"
    second_protocol = second / "protocol.yaml"
    _write_protocol(first_protocol, first_payload)
    _write_protocol(second_protocol, second_payload)
    left = ExperimentEngine().run(first_protocol, tmp_path / "left-run")
    right = ExperimentEngine().run(second_protocol, tmp_path / "right-run")
    with pytest.raises(ExperimentExecutionError, match="methodologically incompatible"):
        compare_experiment_runs(left.root, right.root)


def test_nonfinite_dataset_values_fail_closed(tmp_path: Path) -> None:
    (tmp_path / "data.csv").write_text("x1,x2,y\n1,2,3\n2,3,4\n3,nan,5\n4,5,6\n", encoding="utf-8")
    path = tmp_path / "protocol.yaml"
    _write_protocol(path, _protocol_payload(tmp_path))
    with pytest.raises(ExperimentExecutionError, match="not finite"):
        ExperimentEngine().run(path, tmp_path / "runs")


def test_inspect_verifies_before_returning_summary(tmp_path: Path) -> None:
    result = ExperimentEngine().run(REFERENCE_PROTOCOL, tmp_path)
    summary = inspect_experiment_run(result.root)
    assert summary["verification"]["status"] == "PASS"
    assert summary["experiment_id"] == "REFERENCE-REGRESSION-001"
    assert summary["scientific_result_hash"] == result.scientific_result_hash
    assert len(summary["implementation_hash"]) == 64
