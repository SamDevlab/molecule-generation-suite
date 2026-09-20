from __future__ import annotations

from copy import deepcopy
import csv
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

import pytest

pytest.importorskip("rdkit")
from rdkit import Chem

from research_os.molecular_discovery.experimental_handoff import (
    EXPERIMENT_ID,
    PANEL_KEYS,
    ExperimentalHandoffError,
    generate_handoff,
    load_frozen_panel,
    protocol_freeze_gate,
    validate_handoff_manifest,
)
from research_os.molecular_discovery.moldisc019 import MOLDISC019Error, ingest_result, validate_result


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "experimental_packages" / "biolab-physical-loop-0"
HANDOFF = SOURCE / "BIOEXP-001" / "handoff"


def _sha256_tree(root: Path) -> dict[str, str]:
    import hashlib

    values: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        values[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return values


def test_frozen_panel_identities_round_trip_through_rdkit() -> None:
    records = load_frozen_panel(SOURCE)
    assert [record["panel_key"] for record in records] == list(PANEL_KEYS)
    expected = {
        "A0B0": "DRIAWXDDGSORDT-KKUQBAQOSA-N",
        "A1B0": "NAZMDUVPQSKJEQ-KKUQBAQOSA-N",
        "A0B1": "DMSDTDPQGPRTNA-FDFHNCONSA-N",
        "A1B1": "URHJIBSBOJFXDI-FDFHNCONSA-N",
    }
    assert {record["panel_key"]: record["inchikey"] for record in records} == expected


def test_checked_in_handoff_contains_four_identity_preserving_formats() -> None:
    manifest = validate_handoff_manifest(HANDOFF)
    assert manifest["experiment_id"] == EXPERIMENT_ID
    assert manifest["actual_experiment"] is False
    assert manifest["e4_created"] is False
    assert manifest["experimental_handoff_ready"] is True
    assert manifest["biolab_package_ready"] is True
    assert manifest["next_generation_allowed"] is False

    request = json.loads((HANDOFF / "experiment_request.json").read_text(encoding="utf-8"))
    assert request["protocol_status"] == "AWAITING_EXTERNAL_PROTOCOL_OR_QUOTE"
    assert request["actual_experiment"] is False
    assert request["experimental_handoff_ready"] is True
    assert [item["panel_key"] for item in request["panel"]] == list(PANEL_KEYS)
    assert set(request["unknown"]["protocol_fields"]) >= {"temperature", "pH", "medium", "units"}

    rows = list(csv.DictReader((HANDOFF / "compound_identity_table.csv").open(encoding="utf-8", newline="")))
    assert [row["panel_key"] for row in rows] == list(PANEL_KEYS)
    assert len(list((HANDOFF / "compounds").glob("*.mol"))) == 4
    assert len(list((HANDOFF / "structures").glob("*.svg"))) == 4

    sdf_molecules = [mol for mol in Chem.SDMolSupplier(str(HANDOFF / "panel.sdf"), removeHs=False) if mol is not None]
    assert [mol.GetProp("PANEL_KEY") for mol in sdf_molecules] == list(PANEL_KEYS)
    assert all(Chem.MolToInchiKey(mol) == mol.GetProp("INCHIKEY") for mol in sdf_molecules)
    for panel_key in PANEL_KEYS:
        molecule = Chem.MolFromMolFile(str(HANDOFF / "compounds" / f"{panel_key}.mol"), removeHs=False)
        assert molecule is not None
        assert Chem.MolToInchiKey(molecule) == next(row["inchikey"] for row in rows if row["panel_key"] == panel_key)
        assert (HANDOFF / "structures" / f"{panel_key}.svg").read_text(encoding="utf-8").startswith("<?xml")


def test_handoff_generation_is_deterministic() -> None:
    with TemporaryDirectory() as temporary:
        first = Path(temporary) / "first"
        second = Path(temporary) / "second"
        left = generate_handoff(SOURCE, first, ROOT)
        right = generate_handoff(SOURCE, second, ROOT)
        assert left["package_hash"] == right["package_hash"]
        assert _sha256_tree(first) == _sha256_tree(second)


def test_identity_mismatch_fails_closed_with_expected_and_derived_keys() -> None:
    with TemporaryDirectory() as temporary:
        copied = Path(temporary) / "source"
        shutil.copytree(SOURCE, copied)
        compound_path = copied / "compounds" / "A0B0.json"
        compound = json.loads(compound_path.read_text(encoding="utf-8"))
        compound["inchikey"] = "WRONG-INCHIKEY"
        compound_path.write_text(json.dumps(compound), encoding="utf-8")
        with pytest.raises(ExperimentalHandoffError, match="expected InChIKey WRONG-INCHIKEY; derived DRIAWXDDGSORDT-KKUQBAQOSA-N"):
            generate_handoff(copied, Path(temporary) / "handoff", ROOT)


def test_protocol_freeze_gate_rejects_real_result_until_frozen() -> None:
    proposed = {
        "actual_experiment": True,
        "protocol_status": "PROPOSED",
        "protocol_id": "BIOEXP-001-PROTOCOL-v1",
        "protocol_hash": "a" * 64,
    }
    assert protocol_freeze_gate(proposed)["code"] == "PROTOCOL_NOT_FROZEN"
    frozen = deepcopy(proposed)
    frozen["protocol_status"] = "FROZEN"
    assert protocol_freeze_gate(frozen)["allowed"] is True


def test_synthetic_fixture_is_validatable_but_can_never_create_e4() -> None:
    fixture = json.loads((SOURCE / "external_result_example_TEST_SYNTHETIC.json").read_text(encoding="utf-8"))
    validation = validate_result(fixture, SOURCE)
    assert validation["eligible_for_e4"] is False
    assert any(item["code"] == "TEST_SYNTHETIC_NOT_SCIENTIFIC_EVIDENCE" for item in validation["errors"])

    with pytest.raises(MOLDISC019Error, match="not eligible for E4"):
        ingest_result(fixture, SOURCE)


def test_result_schema_declares_frozen_protocol_gate() -> None:
    schema = json.loads((HANDOFF / "laboratory_result_schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["protocol_status"]["enum"] == [
        "AWAITING_EXTERNAL_PROTOCOL_OR_QUOTE",
        "PROPOSED",
        "FROZEN",
    ]
    assert schema["allOf"][0]["then"]["properties"]["protocol_status"] == {"const": "FROZEN"}
