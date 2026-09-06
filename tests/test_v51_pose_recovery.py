from research_os.docking.pose_recovery import PoseAtom, PoseRecoveryStatus, recover_pose


def atom(name, element, x, y, z):
    return PoseAtom(name, element, x, y, z)


def test_pose_recovery_is_rotation_translation_invariant():
    reference = (atom("C1", "C", 0, 0, 0), atom("O1", "O", 1, 0, 0), atom("N1", "N", 0, 1, 0))
    candidate = (atom("C1", "C", 10, 4, 2), atom("O1", "O", 10, 5, 2), atom("N1", "N", 9, 4, 2))
    result = recover_pose(reference, candidate, ligand_identity="LIG-1")
    assert result.status == PoseRecoveryStatus.VALID
    assert result.mapping_method == "ATOM_NAME"
    assert result.aligned_rmsd_angstrom is not None and result.aligned_rmsd_angstrom < 1e-8
    assert result.diagnostics["evidence_ceiling"] == "E2_COMPUTATIONAL"


def test_pose_recovery_requires_declared_symmetry_and_limits_search():
    reference = (atom("C1", "C", 0, 0, 0), atom("C2", "C", 2, 0, 0), atom("O1", "O", 1, 1, 0))
    candidate = (atom("C1", "C", 2, 0, 0), atom("C2", "C", 0, 0, 0), atom("O1", "O", 1, 1, 0))
    result = recover_pose(reference, candidate, ligand_identity="LIG-2", symmetric_atom_groups=(("C1", "C2"),))
    assert result.valid
    assert result.mapping_method == "SYMMETRY_PERMUTATION"
    assert result.symmetry_permutations_tested == 2
    too_large = recover_pose(reference, candidate, ligand_identity="LIG-2", symmetric_atom_groups=(("C1", "C2"),), max_symmetry_permutations=1)
    assert too_large.status == PoseRecoveryStatus.INDETERMINATE


def test_pose_recovery_does_not_guess_ambiguous_mapping():
    reference = (atom("X", "C", 0, 0, 0), atom("X", "C", 1, 0, 0))
    candidate = (atom("X", "C", 0, 0, 0), atom("X", "C", 1, 0, 0))
    result = recover_pose(reference, candidate, ligand_identity="LIG-3")
    assert result.status == PoseRecoveryStatus.INDETERMINATE
    assert result.reason_code == "AMBIGUOUS_ATOM_MAPPING"
