from __future__ import annotations

from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

from research_os.molecular_discovery import moldisc018


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "programs" / "moldisc-018-reciprocal-holo-validation" / "program.json"


def test_frozen_program_and_exact_twenty_run_plan() -> None:
    config = moldisc018.load_program_config_v18(CONFIG)
    plan = moldisc018.build_execution_plan(config)
    assert len(plan) == 20
    assert [item["case_id"] for item in plan if item["kind"] == "RECIPROCAL_CROSSDOCK" and item["etkdg_seed"] == 42 and item["replicate"] == "RUN_A"] == ["RX-01", "RX-02", "RX-03", "RX-04"]
    assert config["native_context"]["k57_is_generated_candidate"] is False
    assert config["native_context"]["generated_candidate_is_k57"] is False
    assert config["native_context"]["frozen_classification_after_campaign"] == "PARTIALLY_VALIDATED"


def test_kabsch_identity_and_rigid_transform_recover_receptor_only() -> None:
    reference = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 3.0)]
    moving = [(x + 7.0, y - 3.0, z + 2.0) for x, y, z in reference]
    result = moldisc018.kabsch_align(reference, moving)
    assert result["post_alignment_rmsd_angstrom"] < 1e-12
    assert result["pre_alignment_rmsd_angstrom"] > 0.0


def test_no_fit_symmetry_aware_rmsd_preserves_relative_ligand_motion() -> None:
    reference = Chem.AddHs(Chem.MolFromSmiles("CC"))
    params = AllChem.ETKDGv3(); params.randomSeed = 42
    assert AllChem.EmbedMolecule(reference, params) == 0
    moved = Chem.Mol(reference)
    conf = moved.GetConformer()
    for index in range(moved.GetNumAtoms()):
        point = conf.GetAtomPosition(index)
        conf.SetAtomPosition(index, (point.x + 1.0, point.y, point.z))
    result = moldisc018.no_fit_symmetry_aware_rmsd(reference, moved)
    assert result["status"] == "PASS"
    assert abs(result["rmsd_angstrom"] - 1.0) < 1e-6
    assert result["ligand_fit_applied"] is False


def test_symmetric_atom_permutation_is_accepted_but_invalid_graph_is_rejected() -> None:
    reference = Chem.AddHs(Chem.MolFromSmiles("CC"))
    params = AllChem.ETKDGv3(); params.randomSeed = 1337
    assert AllChem.EmbedMolecule(reference, params) == 0
    permuted = Chem.RenumberAtoms(reference, list(reversed(range(reference.GetNumAtoms()))))
    assert moldisc018.no_fit_symmetry_aware_rmsd(reference, permuted)["status"] == "PASS"
    invalid = Chem.AddHs(Chem.MolFromSmiles("CCC"))
    assert moldisc018.no_fit_symmetry_aware_rmsd(reference, invalid)["status"] == "ANALYSIS_INDETERMINATE"


def test_threshold_and_failure_decomposition_are_frozen() -> None:
    for value, expected in ((1.999999, "RANK1_NEAR_NATIVE"), (2.0, "RANK1_NEAR_NATIVE"), (2.000001, "NO_NEAR_NATIVE_POSE_RETURNED")):
        assert moldisc018._failure_class({"technical_status": "PASS", "rank1_rmsd_angstrom": value, "minimum_rmsd_angstrom": value}) == expected
    assert moldisc018._failure_class({"technical_status": "PASS", "rank1_rmsd_angstrom": 4.0, "minimum_rmsd_angstrom": 1.2}) == "NEAR_NATIVE_POSE_MISRANKED"


def test_primary_denominator_is_four_not_conformer_or_replicate_count() -> None:
    config = moldisc018.load_program_config_v18(CONFIG)
    primary = [item for item in moldisc018.build_execution_plan(config) if item["kind"] == "RECIPROCAL_CROSSDOCK" and item["etkdg_seed"] == 42 and item["replicate"] == "RUN_A"]
    assert len(primary) == 4
