from __future__ import annotations

from pathlib import Path

import pytest

from research_os.docking.capability import capability_metadata
from research_os.molecular_discovery.moldisc012 import (
    CANDIDATE_ID,
    CANDIDATE_INCHIKEY,
    CANDIDATE_SMILES,
    CANDIDATE_VARIANT_ID,
    DOCKING_CONTEXT,
    OPERATIONAL_MOLDISC010_HASH,
    PARENT_MOLDISC011_HASH,
    RMSD_BOUNDARY,
    _candidate_identity,
    _pdbqt_scientific_identity,
    _require_prepared,
    _scientific_payload,
    _target_case,
    load_program_config_v12,
)


CONFIG = Path("programs/moldisc-012-step2-demethyl01-crossdock/program.json")


def test_protocol_freezes_upstream_candidate_target_and_score_boundary():
    config = load_program_config_v12(CONFIG)
    assert config["program_id"] == "MOLDISC-012"
    assert config["parent_program"]["program_scientific_hash"] == PARENT_MOLDISC011_HASH
    assert config["parent_program"]["selected_variant_id"] == CANDIDATE_VARIANT_ID
    assert config["parent_program"]["selected_candidate_id"] == CANDIDATE_ID
    assert config["operational_moldisc010"]["program_scientific_hash"] == OPERATIONAL_MOLDISC010_HASH
    assert all(value is False for key, value in config["operational_moldisc010"].items() if key.startswith("score_used_"))
    assert config["candidate"]["canonical_smiles"] == CANDIDATE_SMILES
    assert config["candidate"]["inchikey"] == CANDIDATE_INCHIKEY
    assert config["target"] == {
        "case_id": "ATX-007",
        "pdb_id": "1KZK",
        "native_chem_comp_id": "JE2",
        "ligand_author_chain": "A",
        "receptor_author_chains": ["A", "B"],
        "target": "PROTEASE",
        "resolution_angstrom": 1.09,
        "source_url": "https://www.rcsb.org/structure/1KZK",
        "operational_parent": "REDOCK-003",
    }
    assert config["docking"]["seed"] == 42
    assert config["docking"]["cpu"] == 1
    assert config["docking"]["exhaustiveness"] == 16
    assert config["docking"]["num_modes"] == 20
    assert config["primary_endpoint"]["scientific_success_threshold"] is None
    assert config["primary_endpoint"]["rmsd_to_native_je2"] == RMSD_BOUNDARY


def test_candidate_identity_is_exact_and_parseable():
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
    assert _require_prepared(first, "receptor") != _require_prepared(second, "receptor")
    assert _pdbqt_scientific_identity(first, "receptor") == _pdbqt_scientific_identity(second, "receptor")


def test_scientific_payload_excludes_raw_transport_hashes():
    payload = _scientific_payload(
        config_hash="config",
        candidate_identity={"candidate_id": CANDIDATE_ID},
        native_reference_structure_hash="native",
        receptor_extracted_sha256="extracted",
        starting_conformer={"sha256": "starting"},
        receptor_scientific_identity="receptor-scientific",
        ligand_scientific_identity="ligand-scientific",
        vina_output_scientific_hash="vina-scientific",
        grid={"grid_hash": "grid"},
        pose_scores=[-1.0],
        capability={"capability_status": "PARTIALLY_VALIDATED", "evidence_level": "E2_COMPUTATIONAL"},
        vina_version="AutoDock Vina v1.2.7",
        openbabel_version="Open Babel 3.1.1",
    )
    assert payload["prepared_inputs"] == {"receptor_scientific_identity": "receptor-scientific", "ligand_scientific_identity": "ligand-scientific"}
    assert payload["docking"]["vina_output_scientific_hash"] == "vina-scientific"
    assert "receptor_pdbqt_sha256" not in payload
    assert "ligand_pdbqt_sha256" not in payload
    assert payload["parent"]["moldisc010_score_used_as_success_threshold"] is False


def test_historical_moldisc010_score_is_not_embedded_in_protocol_logic():
    module_text = Path("src/research_os/molecular_discovery/moldisc012.py").read_text(encoding="utf-8")
    config_text = CONFIG.read_text(encoding="utf-8")
    assert "11.03" not in module_text
    assert "11.03" not in config_text
