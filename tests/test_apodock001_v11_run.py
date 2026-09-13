from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess

import pytest

from research_os.core.hashing import sha256_file
from research_os.docking.apodock001_execution import (
    APODOCK001InfrastructureError,
    ExecutionAuthorization,
    ExecutionAuthorizationError,
    ToolIdentity,
)
from research_os.docking.apodock001_v11_run import (
    APODOCK001V11ProspectiveRunner,
    V11_AUTHORIZATION_LABEL,
    V11_TIMEOUT_SECONDS,
)


ROOT = Path(__file__).parents[1]
V11 = ROOT / "configs/apodock001-protocol-freeze-v1.1.json"
V102 = ROOT / "configs/apodock001-protocol-freeze-v1.0.2.json"
BUNDLE = ROOT / "inputs/apodock001/v1.0.2"
VINA_SHA = "f31f774f723bba7bbe6e9d1c47577020eea9a8da16424284c043d22593570644"


def _runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> APODOCK001V11ProspectiveRunner:
    monkeypatch.setattr(
        "research_os.docking.apodock001_v11_run.verify_frozen_input_bundle",
        lambda *args, **kwargs: {},
    )
    return APODOCK001V11ProspectiveRunner(
        spec_path=V11,
        v102_path=V102,
        source_root=BUNDLE,
        run_root=tmp_path / "runs" / "apodock001-v1.1",
        prepared_root=tmp_path / "prepared",
        staging_root=tmp_path / "staging",
        git_sha="a" * 40,
    )


def _prepared(runner: APODOCK001V11ProspectiveRunner, root: Path) -> dict:
    prepared = {}
    for case in runner.cases:
        prepared[case.case_id] = {}
        for kind in ("receptor", "ligand"):
            path = root / case.case_id / f"{kind}.pdbqt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"fixture {case.case_id} {kind}\n".encode())
            prepared[case.case_id][kind] = {
                "case_id": case.case_id,
                "artifact_kind": kind,
                "source_hashes": deepcopy(case.input_hashes),
                "chemistry": deepcopy(case.chemistry),
                "preparation": deepcopy(case.preparation[kind]),
                "output_path": str(path),
                "output_sha256": sha256_file(path),
                "expected_destination": getattr(case, f"{kind}_prepared_output"),
                "protocol_id": runner.plan.protocol_id,
                "planned_run_id": runner.plan.planned_run_id,
            }
    return prepared


def _tools(tmp_path: Path) -> tuple[ToolIdentity, ToolIdentity]:
    vina_path = tmp_path / "vina_1.2.7"
    obabel_path = tmp_path / "obabel"
    vina_path.write_bytes(b"synthetic tool identity")
    obabel_path.write_bytes(b"synthetic tool identity")
    options = ("-h", "--partialcharge", "gasteiger", "-xr")
    return (
        ToolIdentity(
            "AutoDock Vina", str(vina_path), "1.2.7", "AutoDock Vina 1.2.7",
            VINA_SHA, VINA_SHA, "1.2.7",
        ),
        ToolIdentity(
            "Open Babel", str(obabel_path), "3.1.1", "Open Babel 3.1.1",
            "b" * 64, None, "3.1.1", options,
        ),
    )


def test_runner_uses_v11_identity_and_frozen_case_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    assert runner.plan.protocol_id == "research-os.apodock001.protocol.v1.1+b1a3c7b16db63ea4"
    assert runner.plan.protocol_hash == "b1a3c7b16db63ea426202a82db2551cc07301e34ea5584bfab75706681481a9e"
    assert runner.plan.planned_run_id == "research-os.apodock001.planned-run.v2+96c21ae483c16db7"
    assert [case.case_id for case in runner.cases] == [f"APD-{index:03d}" for index in range(1, 11)]
    assert all(case.vina["exhaustiveness"] == 32 for case in runner.cases)


def test_preflight_is_unauthorized_and_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    report = runner.preflight()
    assert report["status"] == "READY_FOR_EXPLICIT_AUTHORIZATION"
    assert report["execution_authorized"] is False
    assert report["prospective_execution_started"] is False
    assert report["run_id"] is None
    assert report["results"] == []
    assert report["scores"] == []
    assert report["poses"] == []


def test_wrong_authorization_blocks_before_subprocess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    prepared = _prepared(runner, tmp_path / "prepared-source")
    vina, obabel = _tools(tmp_path)
    with pytest.raises(ExecutionAuthorizationError):
        runner.execute_prospective(
            vina=vina,
            openbabel=obabel,
            prepared_artifacts=prepared,
            authorization=ExecutionAuthorization(True, "APODOCK-001-v1.0.2"),
            checkpoint_path=tmp_path / "checkpoint.json",
        )
    assert not runner.run_root.exists()


def test_default_authorization_blocks_before_subprocess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    with pytest.raises(ExecutionAuthorizationError):
        runner.execute_prospective(
            vina=_tools(tmp_path)[0],
            openbabel=_tools(tmp_path)[1],
            prepared_artifacts={},
            authorization=ExecutionAuthorization(),
            checkpoint_path=tmp_path / "checkpoint.json",
        )
    assert not runner.run_root.exists()


def test_existing_run_root_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    runner.run_root.mkdir(parents=True)
    (runner.run_root / "existing").write_text("already present", encoding="utf-8")
    with pytest.raises(Exception):
        runner.preflight()


def test_command_audit_is_exact_v11_surface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    commands = runner.command_audit("/tmp/vina_1.2.7")
    assert len(commands) == 10
    for record in commands:
        command = record["command"]
        assert command[command.index("--exhaustiveness") + 1] == "32"
        assert command[command.index("--cpu") + 1] == "1"
        assert command[command.index("--seed") + 1] == "42"
        assert command[command.index("--num_modes") + 1] == "20"
        assert "--energy_range" not in command


def test_missing_prepared_artifact_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    prepared = _prepared(runner, tmp_path / "prepared-source")
    prepared["APD-001"].pop("ligand")
    with pytest.raises(APODOCK001InfrastructureError):
        runner.verify_prepared_artifacts(prepared)


def test_prepared_hash_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    prepared = _prepared(runner, tmp_path / "prepared-source")
    prepared["APD-002"]["receptor"]["output_sha256"] = "0" * 64
    with pytest.raises(APODOCK001InfrastructureError):
        runner.verify_prepared_artifacts(prepared)


def test_checkpoint_contains_all_pre_execution_gates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    prepared = _prepared(runner, tmp_path / "prepared-source")
    vina, obabel = _tools(tmp_path)
    checkpoint = runner.write_pre_execution_checkpoint(
        tmp_path / "checkpoint.json",
        vina=vina,
        openbabel=obabel,
        prepared_artifacts=prepared,
        commands=runner.command_audit(vina.executable),
    )
    assert checkpoint["prepared_receptors"] == 10
    assert checkpoint["prepared_ligands"] == 10
    assert checkpoint["prepared_artifacts"] == 20
    assert checkpoint["command_audit_count"] == 10
    assert checkpoint["timeout_seconds"] == 1800
    assert checkpoint["retry_count"] == 0
    assert checkpoint["run_id"] is None
    assert checkpoint["execution_authorized"] is False
    assert checkpoint["prospective_execution_started"] is False


def _fake_vina_run(calls: list[tuple[str, ...]], *, timeout_case: str | None = None):
    def fake(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        stdout = kwargs["stdout"]
        stderr = kwargs["stderr"]
        stdout.write(b"synthetic stdout\n")
        stderr.write(b"synthetic stderr\n")
        if timeout_case and timeout_case in str(command[command.index("--receptor") + 1]):
            raise subprocess.TimeoutExpired(command, V11_TIMEOUT_SECONDS)
        output = Path(command[command.index("--out") + 1])
        output.write_text(
            "MODEL 1\nREMARK VINA RESULT: -5.0 0.0 0.0\nENDMDL\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)
    return fake


def test_authorized_execution_makes_ten_attempts_and_seals_v2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    prepared = _prepared(runner, tmp_path / "prepared-source")
    vina, obabel = _tools(tmp_path)
    checkpoint_path = tmp_path / "checkpoint.json"
    runner.write_pre_execution_checkpoint(
        checkpoint_path,
        vina=vina,
        openbabel=obabel,
        prepared_artifacts=prepared,
        commands=runner.command_audit(vina.executable),
    )
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(subprocess, "run", _fake_vina_run(calls))
    manifest = runner.execute_prospective(
        vina=vina,
        openbabel=obabel,
        prepared_artifacts=prepared,
        authorization=ExecutionAuthorization(True, V11_AUTHORIZATION_LABEL),
        checkpoint_path=checkpoint_path,
        environment_manifest={"schema_version": "test"},
    )
    assert len(calls) == 10
    assert [command[command.index("--receptor") + 1].split("prepared\\")[-1].split("/receptor")[0].split("\\")[-1] for command in calls]
    assert manifest["status"] == "RAW_RESULTS_SEALED"
    assert manifest["raw_results_sealed"] is True
    assert manifest["protocol_hash"] == runner.plan.protocol_hash
    assert manifest["planned_run_id"] == runner.plan.planned_run_id
    seal = __import__("json").loads((runner.run_root / "raw-results-seal.json").read_text(encoding="utf-8"))
    assert seal["schema_version"] == "research-os.apodock001.raw-results-seal.v2"
    assert seal["protocol_hash"] == runner.plan.protocol_hash
    assert seal["planned_run_id"] == runner.plan.planned_run_id
    assert seal["run_id"] == manifest["run_id"]
    assert len(seal["raw_output_hashes"]) == 10


def test_timeout_is_failed_once_without_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _runner(tmp_path, monkeypatch)
    prepared = _prepared(runner, tmp_path / "prepared-source")
    vina, obabel = _tools(tmp_path)
    checkpoint_path = tmp_path / "checkpoint.json"
    runner.write_pre_execution_checkpoint(
        checkpoint_path,
        vina=vina,
        openbabel=obabel,
        prepared_artifacts=prepared,
        commands=runner.command_audit(vina.executable),
    )
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(subprocess, "run", _fake_vina_run(calls, timeout_case="APD-006"))
    manifest = runner.execute_prospective(
        vina=vina,
        openbabel=obabel,
        prepared_artifacts=prepared,
        authorization=ExecutionAuthorization(True, V11_AUTHORIZATION_LABEL),
        checkpoint_path=checkpoint_path,
        environment_manifest={"schema_version": "test"},
    )
    assert len(calls) == 10
    record = next(record for record in manifest["cases"] if record["case_id"] == "APD-006")
    assert record["status"] == "FAILED"
    assert record["failure_stage"] == "ADAPTER_SUBPROCESS_TIMEOUT"
    assert record["retry_count"] == 0
    assert record["raw_output_sha256"] is None
    assert record["timeout_classification"]["timeout_seconds"] == 1800
