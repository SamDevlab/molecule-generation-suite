from __future__ import annotations

from pathlib import Path

import pytest

from research_os.docking.capability import capability_metadata
from research_os.molecular_discovery.moldisc010 import (
    CANDIDATE_ID,
    CANDIDATE_INCHIKEY,
    CANDIDATE_SMILES,
    DOCKING_CONTEXT,
    PARENT_PROGRAM_HASH,
    _pdbqt_scientific_identity,
    _require_prepared,
    _scientific_payload,
    _candidate_identity,
    _target_case,
    load_program_config_v10,
)


CONFIG = Path("programs/moldisc-010-demethyl03-crossdock/program.json")


def test_moldisc_010_protocol_freezes_parent_candidate_target_and_docking_context():
    config = load_program_config_v10(CONFIG)
    assert config["program_id"] == "MOLDISC-010"
    assert config["program_version"] == "1.0"
    assert config["parent_program"]["program_scientific_hash"] == PARENT_PROGRAM_HASH
    assert config["parent_program"]["selected_candidate_id"] == CANDIDATE_ID
    assert config["candidate"]["canonical_smiles"] == CANDIDATE_SMILES
    assert config["candidate"]["inchikey"] == CANDIDATE_INCHIKEY
    assert config["target"]["case_id"] == "ATX-007"
    assert config["target"]["pdb_id"] == "1KZK"
    assert config["target"]["receptor_author_chains"] == ["A", "B"]
    assert config["docking"]["docking_context"] == DOCKING_CONTEXT
    assert config["docking"]["vina_version_required"] == "1.2.7"
    assert config["docking"]["seed"] == 42
    assert config["docking"]["cpu"] == 1
    assert config["docking"]["exhaustiveness"] == 16
    assert config["docking"]["num_modes"] == 20
    assert config["primary_endpoint"]["rmsd_to_native_je2"] == "NOT_APPLICABLE_DIFFERENT_LIGAND_GRAPH"


def test_demethyl03_identity_is_exact_and_parseable():
    pytest.importorskip("rdkit")
    molecule, smiles, key = _candidate_identity()
    assert molecule is not None
    assert smiles == CANDIDATE_SMILES
    assert key == CANDIDATE_INCHIKEY


def test_target_is_exact_frozen_redock003_atx007_case():
    case = _target_case()
    assert case.case_id == "ATX-007"
    assert case.pdb_id == "1KZK"
    assert case.ligand_id == "JE2"
    assert case.ligand_author_chain == "A"
    assert tuple(case.receptor_author_chains) == ("A", "B")


def test_non_cognate_holo_capability_boundary_remains_partial_e2():
    metadata = capability_metadata(DOCKING_CONTEXT)
    assert metadata["docking_context"] == DOCKING_CONTEXT
    assert metadata["capability_status"] == "PARTIALLY_VALIDATED"
    assert metadata["evidence_level"] == "E2_COMPUTATIONAL"
    assert "CROSSDOCK-001" in metadata["validation_sources"]


def _write_test_pdbqt(path: Path, remark: str, atom_line: str) -> None:
    path.write_text(f"REMARK  Name = {remark}\n{atom_line}\nTER\n", encoding="utf-8")


def test_pdbqt_transport_metadata_does_not_change_scientific_identity(tmp_path: Path):
    atom_line = "ATOM      1  C   LIG A   1       1.000   2.000   3.000  0.00  0.00    +0.123 C "
    first = tmp_path / "first.pdbqt"
    second = tmp_path / "second.pdbqt"
    _write_test_pdbqt(first, "/tmp/run-a/receptor.pdb", atom_line)
    _write_test_pdbqt(second, "/tmp/run-b/receptor.pdb", atom_line)

    first_transport_hash = _require_prepared(first, "receptor")
    second_transport_hash = _require_prepared(second, "receptor")

    assert first_transport_hash != second_transport_hash
    assert _pdbqt_scientific_identity(first, "receptor") == _pdbqt_scientific_identity(second, "receptor")


def test_pdbqt_scientific_changes_change_identity(tmp_path: Path):
    original = tmp_path / "original.pdbqt"
    changed = tmp_path / "changed.pdbqt"
    atom_line = "ATOM      1  C   LIG A   1       1.000   2.000   3.000  0.00  0.00    +0.123 C "
    changed_atom_line = atom_line.replace("   3.000", "   3.100")
    _write_test_pdbqt(original, "/tmp/run-a/receptor.pdb", atom_line)
    _write_test_pdbqt(changed, "/tmp/run-b/receptor.pdb", changed_atom_line)

    assert _pdbqt_scientific_identity(original, "receptor") != _pdbqt_scientific_identity(changed, "receptor")


def test_scientific_payload_keeps_prepared_input_identity_separate_from_raw_hashes():
    payload = _scientific_payload(
        config_hash="config",
        candidate_identity={"candidate_id": "candidate"},
        native_reference_structure_hash="native",
        receptor_extracted_sha256="extracted",
        starting_conformer={"sha256": "starting"},
        receptor_scientific_identity="receptor-scientific",
        ligand_scientific_identity="ligand-scientific",
        grid={"grid_hash": "grid"},
        pose_scores=[-1.0],
        capability={"capability_status": "PARTIALLY_VALIDATED", "evidence_level": "E2_COMPUTATIONAL"},
        vina_version="AutoDock Vina v1.2.7",
        openbabel_version="Open Babel 3.1.1",
    )

    assert payload["prepared_inputs"] == {
        "receptor_scientific_identity": "receptor-scientific",
        "ligand_scientific_identity": "ligand-scientific",
    }
    assert "receptor_pdbqt_sha256" not in payload["prepared_inputs"]
    assert "ligand_pdbqt_sha256" not in payload["prepared_inputs"]
