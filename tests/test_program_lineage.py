from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest
import yaml

from research_os.cli import main
from research_os.programs import (
    DeclarativeProgramRunner,
    ProgramProtocolError,
    ResearchProgram,
    ResearchProgramController,
    ResearchProgramStore,
    ResearchProgramStatus,
    inspect_program_execution,
    verify_program_execution,
)


def _dataset(path: Path) -> None:
    rows = ["x1,x2,y"]
    for index in range(20):
        x1 = float(index)
        x2 = float((index * index + 3) % 11)
        rows.append(f"{x1},{x2},{1.25 + 2.0 * x1 - 0.5 * x2}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _experiment(path: Path, experiment_id: str, *, metric: str = "r2") -> None:
    path.write_text(yaml.safe_dump({
        "protocol": "research-os.declarative-experiment.v1",
        "experiment": {"id": experiment_id, "task": "regression", "seed": 42},
        "dataset": {"adapter": "csv", "path": "data.csv", "target": "y", "features": ["x1", "x2"]},
        "split": {"strategy": "random", "train_fraction": 0.8},
        "models": [{"id": "ols", "adapter": "linear_regression"}],
        "metrics": ["mae", "rmse", metric],
        "evidence": {"require_dataset_hash": True, "require_protocol_hash": True, "fail_closed": True},
    }, sort_keys=False), encoding="utf-8")


def _campaign(path: Path, child: Path, campaign_id: str, *, metric: str = "r2") -> None:
    _experiment(child, campaign_id, metric=metric)
    path.write_text(yaml.safe_dump({
        "schema_version": "research-os.campaign.v1",
        "campaign": {"title": campaign_id, "domain": "ml", "objective": "fixture", "hypothesis": "fixture"},
        "limits": {"max_runs": 2, "max_failures": 1},
        "execution": {"mode": "static", "retry_count": 0, "failure_policy": "continue_independent"},
        "experiments": [{"experiment_id": "experiment", "protocol": child.name}],
        "analysis": {"multiplicity": {"family_id": f"family-{campaign_id}", "mode": "DESCRIPTIVE_ONLY", "comparisons": []}},
    }, sort_keys=False), encoding="utf-8")


def _program(path: Path, campaigns: list[dict], *, max_campaigns: int = 6, max_runs: int = 10, max_failures: int = 2) -> None:
    ids = [item["local_id"] for item in campaigns]
    path.write_text(yaml.safe_dump({
        "schema_version": "research-os.program.v1",
        "program": {"program_id": "PROG-FIXTURE", "title": "Fixture program", "domain": "ml", "objective": "preserve campaign lineage", "motivation": "verify durable provenance", "initial_problem": "lineage is incomplete", "research_questions": [{"question_id": "Q-1", "question": "does the tree verify?", "gap_it_attempts_to_resolve": "durable lineage"}], "evidence_target": "E2_COMPUTATIONAL"},
        "limits": {"max_campaigns": max_campaigns, "max_runs": max_runs, "max_failures": max_failures},
        "execution": {"mode": "STATIC_PREDECLARED", "retry_count": 0, "failure_policy": "continue_independent"},
        "campaigns": campaigns,
        "synthesis": {"mode": "STRUCTURAL_ONLY", "primary_campaigns": ids[:1], "complementary_campaigns": ids[1:]},
    }, sort_keys=False), encoding="utf-8")


def test_program_protocol_identity_is_operationally_neutral(tmp_path: Path) -> None:
    _dataset(tmp_path / "data.csv")
    _campaign(tmp_path / "a.yaml", tmp_path / "a-child.yaml", "a")
    _campaign(tmp_path / "b.yaml", tmp_path / "b-child.yaml", "b")
    _program(tmp_path / "program.yaml", [{"local_id": "a", "protocol_path": "a.yaml"}, {"local_id": "b", "protocol_path": "b.yaml", "depends_on": ["a"]}])
    runner = DeclarativeProgramRunner()
    first = runner.plan(tmp_path / "program.yaml")
    raw = yaml.safe_load((tmp_path / "program.yaml").read_text(encoding="utf-8"))
    raw["program"]["title"] = "same scientific program"
    (tmp_path / "program.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    assert runner.plan(tmp_path / "program.yaml").program_protocol_id != first.program_protocol_id
    raw["program"]["title"] = "Fixture program"
    raw["program"]["objective"] = "preserve campaign lineage"
    raw["program"]["motivation"] = "verify durable provenance"
    raw["program"]["initial_problem"] = "lineage is incomplete"
    (tmp_path / "program.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    second = runner.plan(tmp_path / "program.yaml")
    assert second.program_protocol_id == first.program_protocol_id


def test_program_limits_and_cycle_fail_closed(tmp_path: Path) -> None:
    _dataset(tmp_path / "data.csv")
    _campaign(tmp_path / "a.yaml", tmp_path / "a-child.yaml", "a")
    _campaign(tmp_path / "b.yaml", tmp_path / "b-child.yaml", "b")
    _program(tmp_path / "too-many.yaml", [{"local_id": "a", "protocol_path": "a.yaml"}, {"local_id": "b", "protocol_path": "b.yaml"}], max_campaigns=1)
    with pytest.raises(ProgramProtocolError, match="max_campaigns"):
        DeclarativeProgramRunner().plan(tmp_path / "too-many.yaml")
    _program(tmp_path / "cycle.yaml", [{"local_id": "a", "protocol_path": "a.yaml", "depends_on": ["b"]}, {"local_id": "b", "protocol_path": "b.yaml", "depends_on": ["a"]}])
    with pytest.raises(ProgramProtocolError, match="cycle"):
        DeclarativeProgramRunner().plan(tmp_path / "cycle.yaml")


def test_program_protocol_rejects_absolute_campaign_paths(tmp_path: Path) -> None:
    _dataset(tmp_path / "data.csv")
    _campaign(tmp_path / "a.yaml", tmp_path / "a-child.yaml", "a")
    _program(tmp_path / "program.yaml", [{"local_id": "a", "protocol_path": str((tmp_path / "a.yaml").resolve())}])
    with pytest.raises(ProgramProtocolError, match="relative"):
        DeclarativeProgramRunner().plan(tmp_path / "program.yaml")


def test_full_program_lineage_survives_restart_and_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _dataset(tmp_path / "data.csv")
    _campaign(tmp_path / "a.yaml", tmp_path / "a-child.yaml", "a")
    _campaign(tmp_path / "b.yaml", tmp_path / "b-child.yaml", "b")
    _program(tmp_path / "program.yaml", [{"local_id": "a", "protocol_path": "a.yaml"}, {"local_id": "b", "protocol_path": "b.yaml", "depends_on": ["a"]}])
    root = tmp_path / "program-execution"
    assert main(["program", "plan", str(tmp_path / "program.yaml")]) == 0
    assert json.loads(capsys.readouterr().out)["execution_order"] == ["a", "b"]
    manifest = DeclarativeProgramRunner().run(tmp_path / "program.yaml", root)
    assert manifest["status"] == "COMPLETED"
    assert manifest["scientific_status"] == "UNASSESSED"
    assert manifest["evidence_level"] == "E2_COMPUTATIONAL"
    assert all(item["status"] == "COMPLETED" for item in manifest["campaigns"].values())
    assert verify_program_execution(root).status == "PASS"
    store = ResearchProgramStore(root / "program-store.sqlite3")
    restored = store.get_execution(manifest["program_execution_id"])
    store.close()
    assert restored["record_hash"] == manifest["record_hash"]
    assert inspect_program_execution(root)["verification"]["status"] == "PASS"
    assert main(["program", "verify", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"
    assert main(["program", "inspect", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["program_execution_id"] == manifest["program_execution_id"]
    connection = sqlite3.connect(root / "program-store.sqlite3")
    connection.execute("UPDATE research_programs SET payload_json = replace(payload_json, 'Fixture program', 'tampered program') WHERE program_id = ?", ("PROG-FIXTURE",))
    connection.commit()
    connection.close()
    assert verify_program_execution(root).first_loss == "PROGRAM_SNAPSHOT_DIGEST_MISMATCH"


def test_failure_isolation_preserves_failed_independent_and_dependency_skip(tmp_path: Path) -> None:
    _dataset(tmp_path / "data.csv")
    _campaign(tmp_path / "a.yaml", tmp_path / "a-child.yaml", "a")
    _campaign(tmp_path / "bad.yaml", tmp_path / "bad-child.yaml", "bad", metric="not-registered")
    _campaign(tmp_path / "c.yaml", tmp_path / "c-child.yaml", "c")
    _campaign(tmp_path / "d.yaml", tmp_path / "d-child.yaml", "d")
    _program(tmp_path / "program.yaml", [{"local_id": "a", "protocol_path": "a.yaml"}, {"local_id": "bad", "protocol_path": "bad.yaml"}, {"local_id": "c", "protocol_path": "c.yaml"}, {"local_id": "d", "protocol_path": "d.yaml", "depends_on": ["bad"]}], max_failures=2)
    manifest = DeclarativeProgramRunner().run(tmp_path / "program.yaml", tmp_path / "execution")
    assert manifest["campaigns"]["bad"]["status"] == "FAILED"
    assert manifest["campaigns"]["c"]["status"] == "COMPLETED"
    assert manifest["campaigns"]["d"]["status"] == "SKIPPED_DEPENDENCY"
    assert manifest["campaigns"]["bad"]["attempts"] == 1
    assert verify_program_execution(tmp_path / "execution").status == "PASS"


def test_program_tampering_and_undeclared_campaign_fail_closed(tmp_path: Path) -> None:
    _dataset(tmp_path / "data.csv")
    _campaign(tmp_path / "a.yaml", tmp_path / "a-child.yaml", "a")
    _program(tmp_path / "program.yaml", [{"local_id": "a", "protocol_path": "a.yaml"}])
    root = tmp_path / "execution"
    DeclarativeProgramRunner().run(tmp_path / "program.yaml", root)
    manifest_path = root / "program-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["status"] = "TAMPERED"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    assert verify_program_execution(root).first_loss == "PROGRAM_RECORD_HASH_MISMATCH"
    manifest_path.write_text(json.dumps({**payload, "record_hash": "0" * 64}), encoding="utf-8")
    (root / "campaigns" / "rogue").mkdir()
    assert verify_program_execution(root).status == "FAIL"


def test_snapshot_digest_and_controller_limits_remain_compatible(tmp_path: Path) -> None:
    program = ResearchProgram("P", "title", "domain", "objective", "motivation", "problem", max_runs=1, max_failures=1)
    assert program.valid
    assert program.snapshot_integrity == program.digest
    with pytest.raises(PermissionError):
        ResearchProgramController(program).transition(max_runs=2)
    store = ResearchProgramStore(tmp_path / "programs.sqlite")
    store.save(program)
    store.close()
    restored_store = ResearchProgramStore(tmp_path / "programs.sqlite")
    restored = restored_store.get("P")
    restored_store.close()
    assert restored.digest == program.digest
    assert restored.valid
