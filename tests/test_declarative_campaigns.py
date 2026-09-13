from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from research_os.campaigns.declarative import (
    CampaignProtocolError,
    DeclarativeCampaignRunner,
    inspect_campaign_execution,
    load_campaign_protocol,
    verify_campaign_execution,
)
from research_os.datasets import DatasetRegistry
from research_os.cli import main


def _dataset(path: Path) -> None:
    rows = ["x1,x2,y"]
    for index in range(20):
        x1 = float(index)
        x2 = float((index * index + 3) % 11)
        rows.append(f"{x1},{x2},{1.25 + 2.0 * x1 - 0.5 * x2}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _experiment(path: Path, experiment_id: str, *, metric: str = "r2", registry: Path | None = None, model_registry: Path | None = None) -> None:
    payload = {
        "protocol": "research-os.declarative-experiment.v1",
        "experiment": {"id": experiment_id, "task": "regression", "seed": 42},
        "dataset": {"adapter": "csv", "path": "data.csv", "target": "y", "features": ["x1", "x2"]},
        "split": {"strategy": "random", "train_fraction": 0.8},
        "models": [{"id": "ols", "adapter": "linear_regression"}],
        "metrics": ["mae", "rmse", metric],
        "evidence": {"require_dataset_hash": True, "require_protocol_hash": True, "fail_closed": True},
    }
    if registry is not None:
        payload["dataset_registry"] = {"enabled": True, "root": str(registry), "dataset_id": "fixture-regression", "version": "1"}
    if model_registry is not None:
        payload["model_registry"] = {"enabled": True, "root": str(model_registry)}
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _campaign(path: Path, experiments: list[dict], *, max_runs: int = 4, max_failures: int = 2) -> None:
    ids = {str(item["experiment_id"]) for item in experiments}
    comparisons = [["baseline", "alternative"]] if {"baseline", "alternative"}.issubset(ids) else ([sorted(ids)[:2]] if len(ids) >= 2 else [])
    payload = {
        "schema_version": "research-os.campaign.v1",
        "campaign": {"title": "Fixture campaign", "domain": "ml", "objective": "compare protocols", "hypothesis": "declared comparison is informative"},
        "limits": {"max_runs": max_runs, "max_failures": max_failures},
        "execution": {"mode": "static", "retry_count": 0, "failure_policy": "continue_independent"},
        "experiments": experiments,
        "analysis": {"multiplicity": {"family_id": "fixture-family", "mode": "DESCRIPTIVE_ONLY", "comparisons": comparisons}},
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_campaign_identity_is_path_and_timestamp_neutral(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for root in (first, second):
        _dataset(root / "data.csv")
        _experiment(root / "child.yaml", "child")
    _campaign(first / "campaign.yaml", [{"experiment_id": "baseline", "protocol": "child.yaml"}])
    _campaign(second / "campaign.yaml", [{"experiment_id": "baseline", "protocol": "child.yaml"}])
    runner = DeclarativeCampaignRunner()
    assert runner.plan(first / "campaign.yaml").campaign_protocol_id == runner.plan(second / "campaign.yaml").campaign_protocol_id
    raw = yaml.safe_load((second / "campaign.yaml").read_text(encoding="utf-8"))
    raw["campaign"]["hypothesis"] = "mutated"
    (second / "campaign.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    assert runner.plan(first / "campaign.yaml").campaign_protocol_id != runner.plan(second / "campaign.yaml").campaign_protocol_id


def test_plan_enforces_limits_and_dependency_cycles(tmp_path: Path) -> None:
    _dataset(tmp_path / "data.csv")
    _experiment(tmp_path / "child.yaml", "child")
    _campaign(tmp_path / "too-many.yaml", [{"experiment_id": "a", "protocol": "child.yaml"}, {"experiment_id": "b", "protocol": "child.yaml"}], max_runs=1)
    with pytest.raises(CampaignProtocolError, match="max_runs"):
        DeclarativeCampaignRunner().plan(tmp_path / "too-many.yaml")
    _campaign(tmp_path / "cycle.yaml", [{"experiment_id": "a", "protocol": "child.yaml", "requires": ["b"]}, {"experiment_id": "b", "protocol": "child.yaml", "requires": ["a"]}])
    with pytest.raises(CampaignProtocolError, match="cycle"):
        DeclarativeCampaignRunner().plan(tmp_path / "cycle.yaml")


def test_dataset_registry_is_verified_before_child_execution(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    _dataset(data)
    registry = DatasetRegistry(root=tmp_path / "dataset-registry")
    registry.register_file(dataset_id="fixture-regression", version="1", schema_id="csv.x1-x2-y.v1", path=data, row_count=20, artifact_mode="managed")
    _experiment(tmp_path / "child.yaml", "child", registry=tmp_path / "dataset-registry")
    _campaign(tmp_path / "campaign.yaml", [{"experiment_id": "baseline", "protocol": "child.yaml"}])
    plan = DeclarativeCampaignRunner().plan(tmp_path / "campaign.yaml")
    assert plan.resolved_protocols["baseline"]["dataset_registry"]["scientific_dataset_id"].startswith("research-os.dataset.scientific.v1+")


def test_run_isolates_children_preserves_models_and_verifies_after_restart(tmp_path: Path) -> None:
    _dataset(tmp_path / "data.csv")
    _experiment(tmp_path / "baseline.yaml", "baseline", model_registry=tmp_path / "baseline-model-registry")
    _experiment(tmp_path / "alternative.yaml", "alternative", model_registry=tmp_path / "alternative-model-registry")
    _campaign(tmp_path / "campaign.yaml", [{"experiment_id": "baseline", "protocol": "baseline.yaml"}, {"experiment_id": "alternative", "protocol": "alternative.yaml"}])
    root = tmp_path / "execution"
    manifest = DeclarativeCampaignRunner().run(tmp_path / "campaign.yaml", root)
    assert manifest["status"] == "COMPLETED"
    assert all(value["status"] == "COMPLETED" for value in manifest["children"].values())
    assert Path(manifest["children"]["baseline"]["root"]).is_file() is False
    assert Path(manifest["children"]["baseline"]["root"]).is_dir()
    assert verify_campaign_execution(root).status == "PASS"
    assert inspect_campaign_execution(root)["verification"]["status"] == "PASS"
    assert (root / "campaign-execution.sqlite3").is_file()
    assert json.loads((root / "analysis-manifest.json").read_text(encoding="utf-8"))["multiplicity"]["declared_comparison_count"] == 1
    with pytest.raises(CampaignProtocolError, match="already exists"):
        DeclarativeCampaignRunner().run(tmp_path / "campaign.yaml", root)


def test_failure_isolation_dependency_skip_and_no_retry(tmp_path: Path) -> None:
    _dataset(tmp_path / "data.csv")
    _experiment(tmp_path / "bad.yaml", "bad", metric="not-registered")
    _experiment(tmp_path / "good.yaml", "good")
    _campaign(tmp_path / "campaign.yaml", [
        {"experiment_id": "bad", "protocol": "bad.yaml"},
        {"experiment_id": "dependent", "protocol": "good.yaml", "requires": ["bad"]},
        {"experiment_id": "independent", "protocol": "good.yaml"},
    ])
    root = tmp_path / "execution"
    manifest = DeclarativeCampaignRunner().run(tmp_path / "campaign.yaml", root)
    assert manifest["children"]["bad"]["status"] == "FAILED"
    assert manifest["children"]["bad"]["attempts"] == 1
    assert manifest["children"]["dependent"]["status"] == "SKIPPED_DEPENDENCY"
    assert manifest["children"]["independent"]["status"] == "COMPLETED"
    assert verify_campaign_execution(root).status == "PASS"


def test_tampered_child_and_undeclared_directory_fail_closed(tmp_path: Path) -> None:
    _dataset(tmp_path / "data.csv")
    _experiment(tmp_path / "child.yaml", "child")
    _campaign(tmp_path / "campaign.yaml", [{"experiment_id": "baseline", "protocol": "child.yaml"}])
    root = tmp_path / "execution"
    DeclarativeCampaignRunner().run(tmp_path / "campaign.yaml", root)
    child_manifest = next((root / "experiments" / "baseline").glob("*/manifest.json"))
    original = child_manifest.read_text(encoding="utf-8")
    payload = json.loads(original)
    payload["status"] = "TAMPERED"
    child_manifest.write_text(json.dumps(payload), encoding="utf-8")
    assert verify_campaign_execution(root).status == "FAIL"
    child_manifest.write_text(original, encoding="utf-8")
    (root / "experiments" / "undeclared").mkdir()
    assert verify_campaign_execution(root).first_loss == "CAMPAIGN_UNDECLARED_RUN"


def test_campaign_metadata_does_not_promote_evidence_or_scientific_support(tmp_path: Path) -> None:
    _dataset(tmp_path / "data.csv")
    _experiment(tmp_path / "child.yaml", "child")
    _campaign(tmp_path / "campaign.yaml", [{"experiment_id": "baseline", "protocol": "child.yaml"}])
    manifest = DeclarativeCampaignRunner().run(tmp_path / "campaign.yaml", tmp_path / "execution")
    assert manifest["analysis"]["scientific_status"] == "UNASSESSED"
    assert manifest["analysis"]["evidence_level"] == "E2_COMPUTATIONAL"


def test_campaign_cli_plan_run_verify_and_inspect(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _dataset(tmp_path / "data.csv")
    _experiment(tmp_path / "child.yaml", "child")
    _campaign(tmp_path / "campaign.yaml", [{"experiment_id": "baseline", "protocol": "child.yaml"}])
    assert main(["campaign", "plan", str(tmp_path / "campaign.yaml")]) == 0
    assert json.loads(capsys.readouterr().out)["execution_order"] == ["baseline"]
    root = tmp_path / "execution"
    assert main(["campaign", "run", str(tmp_path / "campaign.yaml"), "--output", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "COMPLETED"
    assert main(["campaign", "verify", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"
    assert main(["campaign", "inspect", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["verification"]["status"] == "PASS"
