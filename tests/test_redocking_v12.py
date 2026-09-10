from __future__ import annotations

import math

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from research_os.docking.redocking_v12 import (
    FROZEN_REDOCKING_CASES,
    PROTOCOL_ID,
    POSE_SUCCESS_THRESHOLD_ANGSTROM,
    symmetry_aware_pose_rmsd,
)


def _embedded(smiles: str, seed: int = 42) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=seed) == 0
    AllChem.UFFOptimizeMolecule(mol)
    return Chem.RemoveHs(mol)


def _translate(mol: Chem.Mol, dx: float, dy: float, dz: float) -> Chem.Mol:
    moved = Chem.Mol(mol)
    conf = moved.GetConformer()
    for idx in range(moved.GetNumAtoms()):
        point = conf.GetAtomPosition(idx)
        conf.SetAtomPosition(idx, (point.x + dx, point.y + dy, point.z + dz))
    return moved


def _rotate_around_origin_z_90(mol: Chem.Mol) -> Chem.Mol:
    rotated = Chem.Mol(mol)
    conf = rotated.GetConformer()
    for idx in range(rotated.GetNumAtoms()):
        point = conf.GetAtomPosition(idx)
        conf.SetAtomPosition(idx, (-point.y, point.x, point.z))
    return rotated


def test_v12_protocol_and_frozen_cases_are_unchanged():
    assert PROTOCOL_ID == "research-os.redocking.v1.2"
    assert [(c.pdb_id, c.ligand_id, c.receptor_author_chains) for c in FROZEN_REDOCKING_CASES] == [
        ("1STP", "BTN", ("A",)),
        ("3PTB", "BEN", ("A",)),
        ("1HVR", "XK2", ("A", "B")),
        ("1M17", "AQ4", ("A",)),
        ("1IEP", "STI", ("A",)),
    ]


def test_identical_pose_same_frame_is_zero():
    reference = _embedded("CCO")
    result = symmetry_aware_pose_rmsd(reference, Chem.Mol(reference))
    assert result.status == "PASS"
    assert result.rmsd_angstrom == pytest.approx(0.0, abs=1e-8)


def test_translation_is_not_aligned_away():
    reference = _embedded("CCO")
    translated = _translate(reference, 5.0, 0.0, 0.0)
    result = symmetry_aware_pose_rmsd(reference, translated)
    assert result.status == "PASS"
    assert result.rmsd_angstrom == pytest.approx(5.0, abs=1e-6)
    assert result.rmsd_angstrom > POSE_SUCCESS_THRESHOLD_ANGSTROM


def test_rotation_in_shared_frame_is_not_aligned_away():
    reference = _translate(_embedded("CCCO"), 4.0, 1.5, -2.0)
    rotated = _rotate_around_origin_z_90(reference)
    result = symmetry_aware_pose_rmsd(reference, rotated)
    assert result.status == "PASS"
    assert result.rmsd_angstrom is not None
    assert result.rmsd_angstrom > 1.0


def test_atom_renumbering_can_be_resolved_without_coordinate_fitting():
    reference = _embedded("c1ccccc1")
    order = list(reversed(range(reference.GetNumAtoms())))
    renumbered = Chem.RenumberAtoms(reference, order)
    result = symmetry_aware_pose_rmsd(reference, renumbered)
    assert result.status == "PASS"
    assert result.rmsd_angstrom == pytest.approx(0.0, abs=1e-8)


def test_graph_mismatch_is_indeterminate():
    reference = _embedded("CCO")
    predicted = _embedded("CCN")
    result = symmetry_aware_pose_rmsd(reference, predicted)
    assert result.status == "INDETERMINATE"
    assert result.rmsd_angstrom is None
    assert "graphs differ" in (result.reason or "")


def test_diagonal_translation_matches_euclidean_displacement():
    reference = _embedded("CC")
    translated = _translate(reference, 3.0, 4.0, 12.0)
    result = symmetry_aware_pose_rmsd(reference, translated)
    assert result.status == "PASS"
    assert result.rmsd_angstrom == pytest.approx(math.sqrt(3.0**2 + 4.0**2 + 12.0**2), abs=1e-6)
