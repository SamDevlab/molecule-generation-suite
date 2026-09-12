from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess

import pytest
from rdkit import Chem

from research_os.core.hashing import sha256_file
from research_os.docking.apodock001_execution import (
    APODOCK001ExecutionAdapter,
    APODOCK001InfrastructureError,
    ExecutionAuthorization,
    ExecutionAuthorizationError,
    ExistingProspectiveRunError,
    ToolIdentity,
    build_evidence_scaffold,
    build_environment_manifest,
    prepare_ligand_conformer,
    prepare_receptor_input,
    select_receptor_chain,
    verify_openbabel_tool,
    verify_prepared_artifact,
    verify_vina_tool,
)


SPEC = Path(__file__).parents[1] / "configs" / "apodock001-protocol-freeze-v1.0.1.json"
VINA_SHA = "f31f774f723bba7bbe6e9d1c47577020eea9a8da16424284c043d22593570644"


def _adapter(tmp_path: Path) -> APODOCK001ExecutionAdapter:
    return APODOCK001ExecutionAdapter(
        SPEC,
        run_root=tmp_path / "future-run",
        git_sha="7dea47673c5dd1b251661bf43496731a050ba0aa",
    )


def test_execution_plan_is_complete_and_deterministic(tmp_path: Path) -> None:
    first = _adapter(tmp_path / "a")
    second = _adapter(tmp_path / "b")

    assert first.plan.planned_run_id == second.plan.planned_run_id
    assert first.plan.protocol_id == "research-os.apodock001.protocol.v1.0.1+9e293289c9729603"
    assert [case.case_id for case in first.plan.cases] == [f"APD-{n:03d}" for n in range(1, 11)]
    assert first.plan.cases[-1].chemistry["adapter_version"] == "1.0.0"
    assert first.plan.cases[-1].chemistry["output_identity"] == "1586aa91b6a57fdc938ad3ffa8679996e78d73a834624a3af557c5593e2eb052"


def test_command_contains_only_frozen_flags_and_no_energy_range(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    command = adapter.build_command("APD-001", "/opt/vina_1.2.7")
    flags = tuple(item for item in command if item.startswith("--"))

    assert flags == (
        "--receptor", "--ligand", "--center_x", "--center_y", "--center_z",
        "--size_x", "--size_y", "--size_z", "--exhaustiveness", "--cpu",
        "--seed", "--num_modes", "--out",
    )
    assert "--energy_range" not in command
    assert "16" in command
    assert "1" in command
    assert "42" in command
    assert "20" in command


def test_command_builder_does_not_invoke_subprocess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("command construction must not spawn a process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    command = _adapter(tmp_path).build_command("APD-001", "vina")
    assert command[0] == "vina"


def test_default_authorization_blocks_before_subprocess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("unauthorized execution must not spawn a process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(ExecutionAuthorizationError):
        _adapter(tmp_path).execute_case("APD-001", "vina")


def test_vina_hash_and_version_are_fail_closed(tmp_path: Path) -> None:
    executable = tmp_path / "vina"
    executable.write_bytes(b"synthetic-vina-fixture")
    executable.chmod(0o755)
    observed_hash = sha256_file(executable)

    with pytest.raises(APODOCK001InfrastructureError):
        verify_vina_tool(executable, required_version="1.2.7", required_sha256=VINA_SHA, version_output="AutoDock Vina v1.2.7")
    identity = verify_vina_tool(executable, required_version="1.2.7", required_sha256=observed_hash, version_output="AutoDock Vina v1.2.7")
    assert identity.version == "1.2.7"
    with pytest.raises(APODOCK001InfrastructureError):
        verify_vina_tool(executable, required_version="1.2.7", required_sha256=observed_hash.upper(), version_output="AutoDock Vina v1.2.7")
    with pytest.raises(APODOCK001InfrastructureError):
        verify_vina_tool(executable, required_version="1.2.7", required_sha256=observed_hash, version_output="AutoDock Vina v1.2.6")


def test_openbabel_version_and_options_are_fail_closed(tmp_path: Path) -> None:
    executable = tmp_path / "obabel"
    executable.write_bytes(b"synthetic-openbabel-fixture")
    executable.chmod(0o755)
    identity = verify_openbabel_tool(
        executable,
        version_output="Open Babel 3.1.1",
        help_output="-h --partialcharge -xr",
        required_options=("-h", "--partialcharge", "-xr"),
    )
    assert identity.version == "3.1.1"
    with pytest.raises(APODOCK001InfrastructureError):
        verify_openbabel_tool(executable, version_output="Open Babel 3.0.0")
    with pytest.raises(APODOCK001InfrastructureError):
        verify_openbabel_tool(executable, version_output="Open Babel 3.1.1", help_output="-h", required_options=("-xr",))


def test_execution_manifest_mutations_fail_closed(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    changed = deepcopy(adapter.plan.execution_manifest)
    changed["vina"]["seed"] = 7
    with pytest.raises(Exception):
        adapter.verify_execution_manifest(changed)

    changed = deepcopy(adapter.plan.execution_manifest)
    changed["box"]["cases"]["APD-001"]["size"][0] = 21.0
    with pytest.raises(Exception):
        adapter.verify_execution_manifest(changed)

    changed = deepcopy(adapter.plan.execution_manifest)
    changed["chemistry"]["apd010"]["output_identity"] = "changed"
    with pytest.raises(Exception):
        adapter.verify_execution_manifest(changed)


def test_prepared_input_hash_mutation_fails_closed(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    case = adapter.plan.cases[0]
    output = tmp_path / "prepared.pdbqt"
    output.write_text("synthetic prepared fixture\n", encoding="utf-8")
    artifact = {
        "case_id": case.case_id,
        "source_hashes": deepcopy(case.input_hashes),
        "preparation": deepcopy(case.preparation),
        "output_path": str(output),
        "output_sha256": sha256_file(output),
    }
    verify_prepared_artifact(artifact, expected_case=case)
    artifact["source_hashes"]["apo_pdb_sha256"] = "changed"
    with pytest.raises(APODOCK001InfrastructureError):
        verify_prepared_artifact(artifact, expected_case=case)


def test_existing_output_blocks_rerun(tmp_path: Path) -> None:
    root = tmp_path / "future-run"
    (root / "raw" / "APD-001").mkdir(parents=True)
    (root / "raw" / "APD-001" / "vina_poses.pdbqt").write_text("fixture", encoding="utf-8")
    with pytest.raises(ExistingProspectiveRunError):
        _adapter(tmp_path).preflight()


def test_evidence_scaffold_has_no_results(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    environment = build_environment_manifest(
        protocol_id=adapter.plan.protocol_id,
        git_sha=adapter.git_sha,
        vina=None,
        openbabel=None,
    )
    scaffold = build_evidence_scaffold(adapter.plan, git_sha=adapter.git_sha, environment=environment)
    assert scaffold["status"] == "NOT_EXECUTED"
    assert scaffold["run_id"] is None
    assert scaffold["planned_run_id"] == adapter.plan.planned_run_id
    assert scaffold["results"] == []
    assert scaffold["scores"] == []
    assert scaffold["poses"] == []
    assert scaffold["raw_results_sealed"] is False


def test_operational_environment_does_not_change_plan_identity(tmp_path: Path) -> None:
    first = _adapter(tmp_path / "first")
    second = _adapter(tmp_path / "second")
    assert first.plan.planned_run_id == second.plan.planned_run_id
    assert build_environment_manifest(protocol_id=first.plan.protocol_id, git_sha="a", vina=None, openbabel=None)["git_sha"] != build_environment_manifest(protocol_id=first.plan.protocol_id, git_sha="b", vina=None, openbabel=None)["git_sha"]


def test_receptor_selection_is_chain_only_and_fail_closed() -> None:
    text = (
        "ATOM      1  CA  ALA A   1       1.000   2.000   3.000  1.00 20.00           C  \n"
        "HETATM    2  O   HOH A   2       1.000   2.000   3.000  1.00 20.00           O  \n"
    )
    selected = select_receptor_chain(text, "A")
    assert "ATOM" in selected and "HETATM" not in selected
    with pytest.raises(APODOCK001InfrastructureError):
        select_receptor_chain(text, "B")


def test_receptor_input_hash_is_verified(tmp_path: Path) -> None:
    source = tmp_path / "source.pdb"
    source.write_text(
        "ATOM      1  CA  ALA A   1       1.000   2.000   3.000  1.00 20.00           C  \n",
        encoding="utf-8",
    )
    output = tmp_path / "selected.pdb"
    digest = sha256_file(source)
    observed = prepare_receptor_input(source_path=source, output_pdb_path=output, author_chain="A", expected_sha256=digest)
    assert output.is_file()
    assert observed == sha256_file(output)


def test_ligand_conformer_uses_frozen_seed_and_uff_limit(tmp_path: Path) -> None:
    molecule = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    result = prepare_ligand_conformer(molecule, tmp_path / "ligand.sdf", seed=42, uff_max_iters=1000)
    assert result["random_seed"] == 42
    assert result["heavy_atoms"] == 3
    with pytest.raises(APODOCK001InfrastructureError):
        prepare_ligand_conformer(molecule, tmp_path / "other.sdf", seed=7, uff_max_iters=1000)


def test_authorized_execution_is_one_pass_and_seals_raw_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(tmp_path)
    prepared = {}
    for case in adapter.plan.cases:
        path = tmp_path / f"{case.case_id}.prepared.pdbqt"
        path.write_text(f"synthetic prepared fixture {case.case_id}\n", encoding="utf-8")
        prepared[case.case_id] = {
            "case_id": case.case_id,
            "source_hashes": deepcopy(case.input_hashes),
            "preparation": deepcopy(case.preparation),
            "output_path": str(path),
            "output_sha256": sha256_file(path),
        }
    vina = ToolIdentity("AutoDock Vina", "/tmp/vina_1.2.7", "1.2.7", "AutoDock Vina v1.2.7", VINA_SHA, VINA_SHA, "1.2.7")
    openbabel = ToolIdentity("Open Babel", "/usr/bin/obabel", "3.1.1", "Open Babel 3.1.1", "b" * 64, None, "3.1.1")
    calls: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        output = Path(command[command.index("--out") + 1])
        output.write_text("synthetic Vina fixture; no real docking\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "synthetic stdout", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    manifest = adapter.execute_prospective(
        vina=vina,
        openbabel=openbabel,
        prepared_artifacts=prepared,
        authorization=ExecutionAuthorization(True, "APODOCK-001-v1.0.1"),
    )
    assert len(calls) == 10
    assert manifest["status"] == "RAW_RESULTS_SEALED"
    assert manifest["raw_results_sealed"] is True
    assert manifest["run_id"].startswith("research-os.apodock001.run.v1+")
    assert all(record["returncode"] == 0 for record in manifest["cases"])
    assert (adapter.run_root / "raw-results-seal.json").is_file()
