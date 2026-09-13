from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from research_os.docking.apodock001_v11 import (
    APODOCK001V11ExecutionAdapter,
    ExecutionAuthorizationError,
    V11ProtocolValidationError,
    load_and_validate_v11,
    validate_v11_protocol,
    v11_protocol_hash,
    v11_protocol_id,
    write_v11_protocol,
)


ROOT = Path(__file__).parents[1]
V102 = ROOT / "configs/apodock001-protocol-freeze-v1.0.2.json"
V11 = ROOT / "configs/apodock001-protocol-freeze-v1.1.json"
BUNDLE = ROOT / "inputs/apodock001/v1.0.2"


def _protocol() -> dict:
    return load_and_validate_v11(V11, v102_path=V102)


def test_v11_identity_and_single_scientific_change() -> None:
    protocol = _protocol()
    assert protocol["protocol_version"] == "1.1"
    assert protocol["protocol_id"] == "research-os.apodock001.protocol.v1.1+b1a3c7b16db63ea4"
    assert protocol["protocol_hash"] == "b1a3c7b16db63ea426202a82db2551cc07301e34ea5584bfab75706681481a9e"
    assert protocol["operational_metadata"]["planned_run_id"] == "research-os.apodock001.planned-run.v2+96c21ae483c16db7"
    assert protocol["vina"]["exhaustiveness"] == 32
    assert protocol["runtime_policy"]["case_timeout_seconds"] == 1800
    assert protocol["runtime_policy"]["retry_count"] == 0
    assert protocol["failure_policy"]["one_attempt_per_case"] is True
    assert protocol["failure_policy"]["post_result_tuning"] is False


def test_v11_keeps_frozen_scientific_controls() -> None:
    protocol = _protocol()
    v102 = json.loads(V102.read_text(encoding="utf-8"))
    for key in (
        "input_bundle",
        "benchmark",
        "chemistry",
        "receptor_preparation",
        "ligand_preparation",
        "box",
        "analysis",
    ):
        assert protocol[key] == v102[key], key
    for key in (
        "version",
        "binary_sha256",
        "scoring_function",
        "receptor_mode",
        "seed",
        "cpu",
        "num_modes",
        "flags",
        "energy_range_kcal_per_mol",
    ):
        assert protocol["vina"][key] == v102["vina"][key], key
    assert protocol["analysis"]["success_threshold_angstrom"] == 2.0
    assert protocol["chemistry"]["apd010"]["adapter_version"] == "1.0.0"


@pytest.mark.parametrize(
    "path",
    [
        ("benchmark", "cases", 0, "apo_pdb_sha256"),
        ("input_bundle", "bundle_hash"),
        ("chemistry", "apd010", "structural_identity"),
        ("box", "cases", "APD-001", "size"),
        ("vina", "seed"),
        ("vina", "cpu"),
        ("vina", "exhaustiveness"),
        ("vina", "num_modes"),
        ("analysis", "success_threshold_angstrom"),
        ("runtime_policy", "case_timeout_seconds"),
    ],
)
def test_scientific_mutation_fails_closed(path: tuple[object, ...]) -> None:
    protocol = deepcopy(_protocol())
    target = protocol
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    key = path[-1]
    value = target[key]  # type: ignore[index]
    if isinstance(value, str):
        target[key] = "0" * len(value)  # type: ignore[index]
    elif isinstance(value, list):
        target[key] = list(value)  # type: ignore[index]
        target[key][0] = target[key][0] + 1  # type: ignore[index,operator]
    else:
        target[key] = value + 1  # type: ignore[index,operator]
    with pytest.raises(V11ProtocolValidationError):
        validate_v11_protocol(protocol, v102=json.loads(V102.read_text(encoding="utf-8")))


def test_operational_metadata_does_not_change_scientific_identity() -> None:
    protocol = _protocol()
    changed = deepcopy(protocol)
    changed["operational_metadata"]["git_sha"] = "a" * 40
    changed["operational_metadata"]["timestamp"] = "2099-01-01T00:00:00Z"
    assert v11_protocol_hash(changed) == protocol["protocol_hash"]
    assert v11_protocol_id(changed) == protocol["protocol_id"]


def test_generated_manifest_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_v11_protocol(first, V102)
    write_v11_protocol(second, V102)
    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes() == V11.read_bytes()


def test_command_is_frozen_and_never_executes_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    adapter = APODOCK001V11ExecutionAdapter(
        V11,
        v102_path=V102,
        source_root=BUNDLE,
        run_root=tmp_path / "run",
        staging_root=tmp_path / "staging",
        git_sha="test",
    )
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("subprocess called")))
    command = adapter.build_command("APD-001", "/tmp/vina_1.2.7")
    flags = tuple(item for item in command if item.startswith("--"))
    assert flags == (
        "--receptor",
        "--ligand",
        "--center_x",
        "--center_y",
        "--center_z",
        "--size_x",
        "--size_y",
        "--size_z",
        "--exhaustiveness",
        "--cpu",
        "--seed",
        "--num_modes",
        "--out",
    )
    assert "--energy_range" not in command
    assert command[command.index("--exhaustiveness") + 1] == "32"
    assert command[command.index("--seed") + 1] == "42"
    assert command[command.index("--cpu") + 1] == "1"
    assert command[command.index("--num_modes") + 1] == "20"


def test_preflight_is_not_authorized_and_has_no_results(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    adapter = APODOCK001V11ExecutionAdapter(
        V11,
        v102_path=V102,
        source_root=BUNDLE,
        run_root=tmp_path / "run",
        staging_root=tmp_path / "staging",
        git_sha="test",
    )
    monkeypatch.setattr("research_os.docking.apodock001_v11.verify_frozen_input_bundle", lambda *args: {})
    report = adapter.preflight()
    assert report["status"] == "READY_FOR_EXPLICIT_AUTHORIZATION"
    assert report["execution_authorized"] is False
    assert report["prospective_execution_started"] is False
    assert report["run_id"] is None
    assert report["evidence_scaffold_status"] == "NOT_EXECUTED"
    assert report["results"] == []
    assert report["scores"] == []
    assert report["poses"] == []
    assert report["vina_docking_executed"] is False


def test_freeze_adapter_has_no_execution_path() -> None:
    adapter = APODOCK001V11ExecutionAdapter(
        V11,
        v102_path=V102,
        source_root=BUNDLE,
        run_root=Path("/tmp/apodock001-v1.1-test-run"),
        staging_root=Path("/tmp/apodock001-v1.1-test-staging"),
        git_sha="test",
    )
    with pytest.raises(ExecutionAuthorizationError, match="no execution path"):
        adapter.execute_prospective()
