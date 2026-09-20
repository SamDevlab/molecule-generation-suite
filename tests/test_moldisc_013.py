from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Geometry import Point3D

from research_os.molecular_discovery.moldisc013 import (
    CHILD_CANDIDATE_INCHIKEY,
    CHILD_CANDIDATE_SMILES,
    COMMON_CORE_HEAVY_ATOMS,
    GRID_HASH,
    MOLDISC013Error,
    PARENT_CANDIDATE_INCHIKEY,
    PARENT_CANDIDATE_SMILES,
    PARENT_HEAVY_ATOMS,
    load_program_config_v13,
    analyze_pose_pair,
)


CONFIG = Path("programs/moldisc-013-common-core-pose-diagnostic/program.json")


def _molecule(smiles: str, coordinates: list[tuple[float, float, float]]) -> Chem.Mol:
    molecule = Chem.MolFromSmiles(smiles)
    assert molecule is not None
    assert molecule.GetNumAtoms() == len(coordinates)
    conformer = Chem.Conformer(molecule.GetNumAtoms())
    for index, xyz in enumerate(coordinates):
        conformer.SetAtomPosition(index, Point3D(*xyz))
    molecule.AddConformer(conformer, assignId=True)
    return molecule


def test_protocol_freezes_parents_chemistry_target_and_no_score_endpoint():
    config = load_program_config_v13(CONFIG)
    assert config["parents"]["moldisc010"]["program_scientific_hash"] == "360ef9eb66981287781a971a7e09aebbe2749be765af5b4c6dcb33e3839eb48b"
    assert config["parents"]["moldisc012"]["program_scientific_hash"] == "e8c66a7726a3b191723e0dea072afdb5e4d4d9202b142eff83fe6d19c623f776"
    assert config["parent_candidate"]["inchikey"] == PARENT_CANDIDATE_INCHIKEY
    assert config["child_candidate"]["inchikey"] == CHILD_CANDIDATE_INCHIKEY
    assert config["chemistry"]["parent_heavy_atoms"] == PARENT_HEAVY_ATOMS
    assert config["chemistry"]["common_core_heavy_atoms"] == COMMON_CORE_HEAVY_ATOMS
    assert config["target"]["grid_hash"] == GRID_HASH
    assert config["mapping"]["no_rigid_body_alignment"] is True
    assert config["endpoints"]["score_success_threshold"] is None
    assert config["endpoints"]["geometry_threshold"] is None
    assert config["endpoints"]["scores_used_for_pair_selection"] is False


def test_frozen_parent_child_relation_is_exact_heavy_substructure():
    parent = Chem.MolFromSmiles(PARENT_CANDIDATE_SMILES)
    child = Chem.MolFromSmiles(CHILD_CANDIDATE_SMILES)
    assert parent is not None and child is not None
    result = analyze_pose_pair(
        _molecule("CCO", [(0, 0, 0), (1, 0, 0), (2, 0, 0)]),
        _molecule("CO", [(1, 0, 0), (2, 0, 0)]),
        _molecule("CCO", [(0, 0, 0), (1, 0, 0), (2, 0, 0)]),
        _molecule("CO", [(1, 0, 0), (2, 0, 0)]),
    )
    assert result.status == "PASS"
    assert result.common_core_rmsd_angstrom == pytest.approx(0.0)


def test_atom_order_independence():
    parent_source = _molecule("CCO", [(0, 0, 0), (1, 0, 0), (2, 0, 0)])
    child_source = _molecule("CO", [(1, 0, 0), (2, 0, 0)])
    parent_pose = _molecule("CCO", [(0, 0, 0), (1, 0, 0), (2, 0, 0)])
    child_pose = Chem.RenumberAtoms(_molecule("CO", [(1, 0, 0), (2, 0, 0)]), [1, 0])
    assert analyze_pose_pair(parent_source, child_source, parent_pose, child_pose).common_core_rmsd_angstrom == pytest.approx(0.0)


def test_symmetry_chooses_minimum_valid_chemical_mapping():
    parent = _molecule("CCC", [(0, 0, 0), (1, 0, 0), (10, 0, 0)])
    child = _molecule("CC", [(0, 0, 0), (1, 0, 0)])
    result = analyze_pose_pair(parent, child, parent, child)
    assert result.common_core_rmsd_angstrom == pytest.approx(0.0)


def test_receptor_frame_does_not_align_or_center_coordinates():
    parent_source = _molecule("CC", [(0, 0, 0), (1, 0, 0)])
    child_source = _molecule("CC", [(0, 0, 0), (1, 0, 0)])
    parent_pose = _molecule("CC", [(0, 0, 0), (1, 0, 0)])
    translated_child = _molecule("CC", [(1, 0, 0), (2, 0, 0)])
    result = analyze_pose_pair(parent_source, child_source, parent_pose, translated_child)
    assert result.common_core_rmsd_angstrom == pytest.approx(1.0)


def test_chemically_invalid_mapping_fails_closed():
    with pytest.raises(MOLDISC013Error):
        analyze_pose_pair(
            _molecule("CCO", [(0, 0, 0), (1, 0, 0), (2, 0, 0)]),
            _molecule("NN", [(0, 0, 0), (1, 0, 0)]),
            _molecule("CCO", [(0, 0, 0), (1, 0, 0), (2, 0, 0)]),
            _molecule("NN", [(0, 0, 0), (1, 0, 0)]),
        )


def test_nonfinite_coordinates_fail_closed():
    parent = _molecule("CC", [(0, 0, 0), (1, 0, 0)])
    child = _molecule("CC", [(0, 0, 0), (1, 0, 0)])
    bad = _molecule("CC", [(float("nan"), 0, 0), (1, 0, 0)])
    with pytest.raises(MOLDISC013Error):
        analyze_pose_pair(parent, child, parent, bad)


def test_protocol_does_not_embed_a_geometry_threshold():
    text = CONFIG.read_text(encoding="utf-8")
    assert '"geometry_threshold": null' in text
    assert '"score_success_threshold": null' in text
