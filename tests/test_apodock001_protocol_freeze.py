from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from research_os.docking.apodock001_protocol import (
    EXPECTED_VINA_SHA256,
    EXPECTED_VINA_VERSION,
    ProtocolValidationError,
    build_dry_run_report,
    load_and_validate,
    load_protocol,
    protocol_hash,
    protocol_id,
    scientific_payload,
    validate_protocol,
)
from research_os.docking.apodock001_runner import APODOCK001ExecutionError, APODOCK001Runner


SPEC = Path(__file__).parents[1] / "configs" / "apodock001-protocol-freeze-v1.0.json"


def _protocol() -> dict[str, object]:
    return load_and_validate(SPEC)


def test_protocol_schema_is_frozen() -> None:
    assert _protocol()["schema_version"] == "research-os.apodock001.protocol.v1"


def test_protocol_has_exact_case_count() -> None:
    protocol = _protocol()
    assert protocol["benchmark"]["case_count"] == 10
    assert len(protocol["benchmark"]["cases"]) == 10


def test_protocol_case_order_is_frozen() -> None:
    assert _protocol()["benchmark"]["case_order"] == [f"APD-{i:03d}" for i in range(1, 11)]


def test_source_hashes_are_frozen() -> None:
    benchmark = _protocol()["benchmark"]
    assert benchmark["source_list_sha256"] == "3eaa3c45732efa05c1e5f4f468275e8f23e7b82ea9632f5c91dac1a30d62ebfc"
    assert benchmark["case_metadata_sha256"] == "5bd7d26535417c10d124bf6aac1f5355b6c9e8c90bdb01d670b18d0ccff3ab6b"


def test_all_case_input_hashes_are_present() -> None:
    for case in _protocol()["benchmark"]["cases"]:
        assert len(case["apo_pdb_sha256"]) == 64
        assert len(case["holo_pdb_sha256"]) == 64
        assert len(case["holo_reference_coordinate_hash"]) == 64
        assert len(case["transformed_holo_reference_coordinate_hash"]) == 64


def test_apd010_structural_and_final_chemistry_states_are_explicit() -> None:
    case = _protocol()["benchmark"]["cases"][-1]
    assert case["case_id"] == "APD-010"
    assert case["structural_preflight_chemistry_ready_for_vina"] is False
    assert case["chemistry_ready_for_vina"] is True


def test_apd010_adapter_identity_is_frozen() -> None:
    apd010 = _protocol()["chemistry"]["apd010"]
    assert apd010["adapter_id"] == "research-os.apd010.bem-mav"
    assert apd010["adapter_version"] == "1.0.0"
    assert apd010["expected_formula"] == "C12H18O13"
    assert apd010["expected_heavy_atoms"] == 25


def test_apd010_source_identities_are_frozen() -> None:
    apd010 = _protocol()["chemistry"]["apd010"]
    assert apd010["input_identity"] == "9941f9b3975839f101b2a440a1d579d97f081b7bf473c7cde6bed696c64b5956"
    assert apd010["output_identity"] == "1586aa91b6a57fdc938ad3ffa8679996e78d73a834624a3af557c5593e2eb052"
    assert apd010["structural_identity"] == "468c8052ff213fbb3a11f6198b61170e41d4b92353a44461a90326b157bdf306"


def test_box_policy_is_deterministic() -> None:
    box = _protocol()["box"]
    assert box["padding_angstrom"] == 6.0
    assert box["minimum_side_angstrom"] == 20.0
    assert box["maximum_side_angstrom"] == 30.0
    assert box["result_dependent_recalculation"] is False


def test_every_case_has_a_frozen_box_hash() -> None:
    boxes = _protocol()["box"]["cases"]
    assert set(boxes) == {f"APD-{i:03d}" for i in range(1, 11)}
    assert all(len(box["grid_hash"]) == 64 for box in boxes.values())


def test_vina_version_and_binary_hash_are_frozen() -> None:
    vina = _protocol()["vina"]
    assert vina["version"] == EXPECTED_VINA_VERSION
    assert vina["binary_sha256"] == EXPECTED_VINA_SHA256


def test_vina_seed_and_cpu_are_frozen() -> None:
    vina = _protocol()["vina"]
    assert vina["seed"] == 42
    assert vina["cpu"] == 1


def test_vina_sampling_parameters_are_frozen() -> None:
    vina = _protocol()["vina"]
    assert vina["exhaustiveness"] == 16
    assert vina["num_modes"] == 20


def test_energy_range_is_not_silently_used() -> None:
    vina = _protocol()["vina"]
    assert vina["energy_range_kcal_per_mol"] is None
    assert "new protocol version" in vina["energy_range_policy"]


def test_primary_analysis_metric_is_frozen() -> None:
    analysis = _protocol()["analysis"]
    assert analysis["primary_metric"].startswith("same-frame symmetry-aware heavy-atom RMSD")
    assert analysis["pose_selection_primary"] == "pose 1 in Vina output order"
    assert analysis["no_tuning"] is True


def test_protocol_hash_ignores_operational_metadata() -> None:
    protocol = _protocol()
    changed = deepcopy(protocol)
    changed["operational_metadata"] = {"absolute_path": "C:/different/run", "timestamp": "future"}
    assert protocol_hash(changed) == protocol_hash(protocol)
    assert protocol_id(changed) == protocol_id(protocol)
    validate_protocol(changed)


def test_protocol_hash_changes_for_scientific_input_change() -> None:
    changed = deepcopy(_protocol())
    changed["benchmark"]["cases"][0]["apo_pdb_sha256"] = "0" * 64
    assert protocol_hash(changed) != protocol_hash(_protocol())
    with pytest.raises(ProtocolValidationError):
        validate_protocol(changed)


def test_recomputed_scientific_identity_is_still_rejected() -> None:
    changed = deepcopy(_protocol())
    changed["analysis"]["success_threshold_angstrom"] = 1.5
    changed["protocol_hash"] = protocol_hash(changed)
    changed["protocol_id"] = protocol_id(changed)
    with pytest.raises(ProtocolValidationError, match="frozen v1.0 identity"):
        validate_protocol(changed)


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":"a","schema_version":"b"}', encoding="utf-8")
    with pytest.raises(ProtocolValidationError, match="duplicate JSON key"):
        load_protocol(path)


def test_nonfinite_json_numbers_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "nan.json"
    path.write_text('{"value": NaN}', encoding="utf-8")
    with pytest.raises(ProtocolValidationError, match="non-finite"):
        load_protocol(path)


def test_scientific_payload_excludes_only_operational_identity_fields() -> None:
    protocol = _protocol()
    payload = scientific_payload(protocol)
    assert "protocol_id" not in payload
    assert "protocol_hash" not in payload
    assert "operational_metadata" not in payload
    assert "benchmark" in payload
    assert "vina" in payload


def test_dry_run_report_is_explicitly_no_docking(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("dry-run must not spawn a process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    report = build_dry_run_report(_protocol())
    assert report["protocol_status"] == "FROZEN"
    assert report["chemistry_ready"] == "10/10"
    assert report["vina_executed"] is False
    assert report["vina_imported_or_invoked"] is False
    assert report["prospective_boundary_intact"] is True


def test_runner_exposes_only_frozen_execution_manifest() -> None:
    manifest = APODOCK001Runner(SPEC).expected_execution_manifest()
    assert manifest["protocol_id"] == _protocol()["protocol_id"]
    assert manifest["benchmark"]["case_order"] == [f"APD-{i:03d}" for i in range(1, 11)]
    assert set(manifest["box"]["cases"]) == set(manifest["benchmark"]["input_hashes"])


def test_runner_rejects_modified_execution_manifest() -> None:
    runner = APODOCK001Runner(SPEC)
    manifest = runner.expected_execution_manifest()
    manifest["vina"]["seed"] = 7
    with pytest.raises(APODOCK001ExecutionError, match="no docking process"):
        runner.verify_execution_manifest(manifest)


def test_runner_manifest_carries_preparation_and_analysis_contracts() -> None:
    manifest = APODOCK001Runner(SPEC).expected_execution_manifest()
    assert "receptor_preparation" in manifest
    assert "ligand_preparation" in manifest
    assert "analysis" in manifest
    assert "box" in manifest
    assert "boxes" not in manifest


def test_runner_rejects_modified_tool_identity() -> None:
    runner = APODOCK001Runner(SPEC)
    with pytest.raises(APODOCK001ExecutionError, match="version mismatch"):
        runner.verify_tool_identity(vina_version="1.2.6", vina_sha256=EXPECTED_VINA_SHA256)
