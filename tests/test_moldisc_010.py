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
