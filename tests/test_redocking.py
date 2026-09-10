from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from research_os.docking.redocking import (
    FROZEN_REDOCKING_CASES,
    POSE_SUCCESS_THRESHOLD_ANGSTROM,
    RedockingCaseResult,
    derive_redocking_grid,
    evaluate_pose_files,
    summarize_redocking_results,
    symmetry_aware_heavy_atom_rmsd,
)


def _embedded(smiles: str, seed: int = 42) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=seed) == 0
    AllChem.UFFOptimizeMolecule(mol)
    return mol


def _rigid_transform(mol: Chem.Mol) -> Chem.Mol:
    copy = Chem.Mol(mol)
    conf = copy.GetConformer()
    for index in range(copy.GetNumAtoms()):
        point = conf.GetAtomPosition(index)
        # 90-degree rotation around z followed by translation.
        conf.SetAtomPosition(index, (-point.y + 7.0, point.x - 3.0, point.z + 4.0))
    return copy


def _write_sdf(path: Path, molecules: list[Chem.Mol]) -> None:
    writer = Chem.SDWriter(str(path))
    for mol in molecules:
        writer.write(mol)
    writer.close()


def test_frozen_case_set_is_exact_and_unique():
    identity = [(case.pdb_id, case.ligand_id, case.author_chain) for case in FROZEN_REDOCKING_CASES]
    assert identity == [
        ("1STP", "BTN", "A"),
        ("3PTB", "BEN", "A"),
        ("1HVR", "XK2", "A"),
        ("1M17", "AQ4", "A"),
        ("1IEP", "STI", "A"),
    ]
    assert len({case.case_id for case in FROZEN_REDOCKING_CASES}) == 5


def test_identical_pose_has_near_zero_rmsd():
    reference = _embedded("CCO")
    result = symmetry_aware_heavy_atom_rmsd(reference, Chem.Mol(reference))
    assert result.status == "PASS"
    assert result.rmsd_angstrom == pytest.approx(0.0, abs=1e-6)
    assert result.rmsd_le_2_angstrom is True


def test_rigid_rotation_and_translation_are_removed_by_alignment():
    reference = _embedded("c1ccccc1")
    predicted = _rigid_transform(reference)
    result = symmetry_aware_heavy_atom_rmsd(reference, predicted)
    assert result.status == "PASS"
    assert result.rmsd_angstrom == pytest.approx(0.0, abs=1e-5)


def test_symmetry_equivalent_atom_order_is_not_raw_index_rmsd():
    reference = _embedded("c1ccccc1")
    heavy = Chem.RemoveHs(reference)
    order = list(reversed(range(heavy.GetNumAtoms())))
    predicted = Chem.RenumberAtoms(heavy, order)
    predicted = _rigid_transform(predicted)
    result = symmetry_aware_heavy_atom_rmsd(heavy, predicted)
    assert result.status == "PASS"
    assert result.rmsd_angstrom == pytest.approx(0.0, abs=1e-5)


def test_graph_mismatch_fails_closed_without_rmsd():
    reference = _embedded("CCO")
    predicted = _embedded("CCN")
    result = symmetry_aware_heavy_atom_rmsd(reference, predicted)
    assert result.status == "INDETERMINATE"
    assert result.rmsd_angstrom is None
    assert "graphs differ" in result.reason


def test_large_nonrigid_pose_deformation_exceeds_success_threshold():
    reference = Chem.RemoveHs(_embedded("CCCC"))
    predicted = Chem.Mol(reference)
    conf = predicted.GetConformer()
    point = conf.GetAtomPosition(0)
    conf.SetAtomPosition(0, (point.x + 10.0, point.y, point.z))
    result = symmetry_aware_heavy_atom_rmsd(reference, predicted)
    assert result.status == "PASS"
    assert result.rmsd_angstrom is not None
    assert result.rmsd_angstrom > POSE_SUCCESS_THRESHOLD_ANGSTROM
    assert result.rmsd_le_2_angstrom is False


def test_grid_uses_native_ligand_midpoint_and_minimum_side():
    reference = Chem.RemoveHs(_embedded("CCO"))
    conf = reference.GetConformer()
    conf.SetAtomPosition(0, (0.0, 0.0, 0.0))
    conf.SetAtomPosition(1, (2.0, 4.0, 6.0))
    conf.SetAtomPosition(2, (4.0, 8.0, 10.0))
    grid = derive_redocking_grid(reference)
    assert grid.status == "PASS"
    assert (grid.center_x, grid.center_y, grid.center_z) == pytest.approx((2.0, 4.0, 5.0))
    assert grid.size_x == pytest.approx(20.0)
    assert grid.size_y == pytest.approx(20.0)
    assert grid.size_z == pytest.approx(22.0)
    assert len(grid.grid_hash) == 64


def test_grid_fails_out_of_domain_instead_of_silently_enlarging_box():
    reference = Chem.RemoveHs(_embedded("CC"))
    conf = reference.GetConformer()
    conf.SetAtomPosition(0, (0.0, 0.0, 0.0))
    conf.SetAtomPosition(1, (20.0, 0.0, 0.0))
    grid = derive_redocking_grid(reference)
    assert grid.status == "OUT_OF_DOMAIN"
    assert grid.unclamped_size_x == pytest.approx(32.0)
    assert grid.size_x == pytest.approx(30.0)
    assert "larger than 30" in grid.reason


def test_file_evaluator_records_content_hashes_and_all_poses(tmp_path: Path):
    reference = _embedded("CCO")
    pose_1 = _rigid_transform(reference)
    pose_2 = Chem.Mol(reference)
    conf = pose_2.GetConformer()
    point = conf.GetAtomPosition(0)
    conf.SetAtomPosition(0, (point.x + 8.0, point.y, point.z))

    reference_path = tmp_path / "reference.sdf"
    poses_path = tmp_path / "poses.sdf"
    _write_sdf(reference_path, [reference])
    _write_sdf(poses_path, [pose_1, pose_2])

    results = evaluate_pose_files(reference_path, poses_path)
    assert len(results) == 2
    assert all(result.reference_sha256 and len(result.reference_sha256) == 64 for result in results)
    assert all(result.predicted_sha256 and len(result.predicted_sha256) == 64 for result in results)
    assert results[0].status == "PASS"


def test_aggregate_keeps_failed_cases_in_two_angstrom_denominator():
    results = [
        RedockingCaseResult("RDK-001", "PASS", 1.0, 0.8, 20),
        RedockingCaseResult("RDK-002", "PASS", 3.0, 1.2, 20),
        RedockingCaseResult("RDK-003", "INDETERMINATE", None, None, 0, first_loss="PREPARATION_FAILED"),
        RedockingCaseResult("RDK-004", "FAIL", None, None, 0, first_loss="DOCKING_FAILED"),
        RedockingCaseResult("RDK-005", "OUT_OF_DOMAIN", None, None, 0, first_loss="BOX_OUT_OF_DOMAIN"),
    ]
    summary = summarize_redocking_results(results)
    success = summary["pose_1_rmsd_le_2_angstrom"]
    assert success["count"] == 1
    assert success["denominator"] == 5
    assert success["fraction_all_frozen_cases"] == pytest.approx(0.2)
    assert summary["passing_rmsd_cases"] == 2
    assert summary["status_counts"] == {"FAIL": 1, "INDETERMINATE": 1, "OUT_OF_DOMAIN": 1, "PASS": 2}


def test_aggregate_rejects_duplicate_case_ids():
    repeated = [
        RedockingCaseResult("RDK-001", "PASS", 1.0, 1.0, 1),
        RedockingCaseResult("RDK-001", "PASS", 1.0, 1.0, 1),
    ]
    with pytest.raises(ValueError, match="unique"):
        summarize_redocking_results(repeated)
