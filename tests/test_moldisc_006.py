from __future__ import annotations

from pathlib import Path

import pytest

from research_os.docking.capability import capability_metadata
from research_os.molecular_discovery.moldisc006 import (
    CANDIDATE_ID,
    CANDIDATE_SMILES,
    DOCKING_CONTEXT,
    PROGRAM_ID,
    _candidate_identity,
    _target_case,
    load_program_config_v6,
)


CONFIG = Path("programs/moldisc-006-nh-crossdock/program.json")


def test_moldisc_006_protocol_freezes_parent_candidate_target_and_context():
    config = load_program_config_v6(CONFIG)
    assert config["program_id"] == PROGRAM_ID
    assert config["program_version"] == "1.1"
    assert config["parent_program"]["selected_candidate_id"] == CANDIDATE_ID
    assert config["candidate"]["canonical_smiles"] == CANDIDATE_SMILES
    assert config["target"]["case_id"] == "ATX-014"
    assert config["target"]["pdb_id"] == "1P2Y"
    assert config["docking"]["docking_context"] == DOCKING_CONTEXT
    assert config["docking"]["vina_version_required"] == "1.2.7"
    assert config["docking"]["seed"] == 42
    assert config["docking"]["cpu"] == 1
    assert config["docking"]["exhaustiveness"] == 16
    assert config["docking"]["num_modes"] == 20
    assert config["docking"]["receptor_preparation"]["retained_cofactors"] == ["HEM"]
    assert config["docking"]["receptor_preparation"]["selected_author_chains"] == ["A"]
    assert config["docking"]["receptor_preparation"]["engine"] == "Meeko"
    assert config["docking"]["receptor_preparation"]["engine_version_required"] == "0.8.0"
    assert config["docking"]["ligand_preparation"]["engine"] == "Meeko"
    assert config["primary_endpoint"]["rmsd_to_native_nct"] == "NOT_APPLICABLE_DIFFERENT_LIGAND_GRAPH"


def test_selected_nh_candidate_identity_is_parseable_and_canonical():
    pytest.importorskip("rdkit")
    molecule, canonical, inchikey = _candidate_identity()
    assert molecule is not None
    assert canonical == CANDIDATE_SMILES
    assert inchikey
    assert len(inchikey) == 27


def test_target_is_exact_frozen_redock003_atx014_case():
    case = _target_case()
    assert case.case_id == "ATX-014"
    assert case.pdb_id == "1P2Y"
    assert case.ligand_id == "NCT"
    assert case.ligand_author_chain == "A"
    assert tuple(case.receptor_author_chains) == ("A",)


def test_non_cognate_holo_capability_boundary_is_partial_e2():
    metadata = capability_metadata(DOCKING_CONTEXT)
    assert metadata["docking_context"] == DOCKING_CONTEXT
    assert metadata["capability_status"] == "PARTIALLY_VALIDATED"
    assert metadata["evidence_level"] == "E2_COMPUTATIONAL"
    assert "CROSSDOCK-001" in metadata["validation_sources"]
