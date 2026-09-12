from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from research_os.core.hashing import sha256_json
from research_os.docking.apodock001_execution import APODOCK001ExecutionAdapter
from research_os.docking.apodock001_input_bundle import (
    FrozenInputBundleError,
    load_bundle_manifest,
    verify_frozen_input_bundle,
)
from research_os.docking.apodock001_protocol import (
    ProtocolValidationError,
    load_and_validate,
    load_and_validate_v102,
)


ROOT = Path(__file__).parents[1]
V101 = ROOT / "configs/apodock001-protocol-freeze-v1.0.1.json"
V102 = ROOT / "configs/apodock001-protocol-freeze-v1.0.2.json"
BUNDLE = ROOT / "inputs/apodock001/v1.0.2"


def test_v101_manifest_remains_unchanged_and_v102_has_derived_identity() -> None:
    old = load_and_validate(V101)
    new = load_and_validate_v102(V102)
    assert old["protocol_id"] == "research-os.apodock001.protocol.v1.0.1+9e293289c9729603"
    assert new["protocol_id"] == "research-os.apodock001.protocol.v1.0.2+aa40517362e14795"
    assert new["protocol_hash"] == "aa40517362e14795a9ea4747b632fab81b2fc1f5bb49e4c880d9ad38699de03c"
    assert new["input_bundle"]["bundle_id"] == "research-os.apodock001.input-bundle.v1+4be4265fa5917645"


def test_v102_preserves_scientific_docking_contract() -> None:
    old = load_and_validate(V101)
    new = load_and_validate_v102(V102)
    for key in ("benchmark", "chemistry", "receptor_preparation", "ligand_preparation", "box", "vina", "analysis", "prospective_boundary"):
        old_value = deepcopy(old[key])
        new_value = deepcopy(new[key])
        if key == "benchmark":
            for case in old_value["cases"]:
                case.pop("reference_sdf_sha256", None)
            for case in new_value["cases"]:
                case.pop("reference_sdf_sha256", None)
        assert new_value == old_value, key


def test_bundle_is_offline_complete_and_hash_deterministic() -> None:
    protocol = load_and_validate_v102(V102)
    manifest = verify_frozen_input_bundle(protocol, BUNDLE)
    payload = {key: value for key, value in manifest.items() if key not in {"bundle_id", "bundle_hash"}}
    assert manifest["bundle_hash"] == sha256_json(payload)
    assert len(manifest["files"]) == 34
    assert not any("timestamp" in record for record in manifest["files"])


def test_missing_or_mutated_bundle_bytes_fail_closed(tmp_path: Path) -> None:
    protocol = load_and_validate_v102(V102)
    copied = tmp_path / "bundle"
    copied.mkdir()
    for path in BUNDLE.rglob("*"):
        if path.is_file():
            destination = copied / path.relative_to(BUNDLE)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())
    target = copied / "reference-sdf/1FTM-AMQ.sdf"
    target.write_bytes(target.read_bytes() + b"mutation")
    with pytest.raises(FrozenInputBundleError, match="hash mismatch"):
        verify_frozen_input_bundle(protocol, copied)


def test_protocol_bundle_declaration_mutation_fails_closed() -> None:
    protocol = load_and_validate_v102(V102)
    changed = deepcopy(protocol)
    changed["input_bundle"]["bundle_hash"] = "0" * 64
    with pytest.raises(ProtocolValidationError):
        from research_os.docking.apodock001_protocol import validate_protocol_v102

        validate_protocol_v102(changed)


def test_v102_adapter_uses_only_bundle_logical_inputs(tmp_path: Path) -> None:
    adapter = APODOCK001ExecutionAdapter(
        V102,
        source_root=BUNDLE,
        run_root=tmp_path / "future-run",
        staging_root=tmp_path / "staging",
        git_sha="audit",
    )
    assert adapter.plan.cases[0].receptor_input == "pdb/1FTO.pdb"
    assert adapter.plan.cases[0].ligand_input == "reference-sdf/1FTM-AMQ.sdf"
    assert adapter.plan.cases[-1].ligand_input == "apd010/BEM_ideal.sdf+MAV_ideal.sdf"
    assert adapter.plan.protocol_id == "research-os.apodock001.protocol.v1.0.2+aa40517362e14795"
