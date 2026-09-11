from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from rdkit import Chem

from research_os.docking import crossdock001
from research_os.docking.crossdock001_evaluator_v11 import (
    PROTOCOL_ID,
    load_single_unsanitized_pose,
    restore_pose_for_evaluation,
    scientific_result_hash,
)


def _tetramethylammonium_with_coordinates() -> Chem.Mol:
    mol = Chem.MolFromSmiles("C[N+](C)(C)C")
    assert mol is not None
    conf = Chem.Conformer(mol.GetNumAtoms())
    coordinates = (
        (0.0, 0.0, 0.0),
        (1.5, 0.0, 0.0),
        (2.5, 1.0, 0.0),
        (2.5, -1.0, 0.0),
        (1.5, 0.0, 1.5),
    )
    for index, xyz in enumerate(coordinates):
        conf.SetAtomPosition(index, xyz)
    mol.AddConformer(conf)
    return mol


def _coordinate_multiset(mol: Chem.Mol) -> list[tuple[float, float, float]]:
    conf = mol.GetConformer()
    return sorted(
        (
            round(float(conf.GetAtomPosition(index).x), 6),
            round(float(conf.GetAtomPosition(index).y), 6),
            round(float(conf.GetAtomPosition(index).z), 6),
        )
        for index in range(mol.GetNumAtoms())
        if mol.GetAtomWithIdx(index).GetAtomicNum() != 1
    )


def test_invalid_openbabel_like_valence_is_restored_without_moving_coordinates(
    tmp_path: Path,
) -> None:
    template = _tetramethylammonium_with_coordinates()
    predicted = Chem.Mol(template)
    nitrogen = next(atom for atom in predicted.GetAtoms() if atom.GetAtomicNum() == 7)
    nitrogen.SetFormalCharge(0)

    # Make the docked coordinates observably different from the chemistry template.
    pred_conf = predicted.GetConformer()
    for index in range(predicted.GetNumAtoms()):
        point = pred_conf.GetAtomPosition(index)
        pred_conf.SetAtomPosition(index, (point.x + 7.0, point.y - 3.0, point.z + 2.0))

    raw_path = tmp_path / "pose_01.sdf"
    writer = Chem.SDWriter(str(raw_path))
    writer.write(predicted)
    writer.close()

    # Sanitized parsing rejects the neutral tetravalent N representation, while
    # the v1.1 loader deliberately keeps coordinates/graph available for repair.
    sanitized = Chem.SDMolSupplier(str(raw_path), removeHs=False, sanitize=True)
    assert [mol for mol in sanitized if mol is not None] == []
    raw = load_single_unsanitized_pose(raw_path)

    restored_path = tmp_path / "pose_01_chemistry_restored.sdf"
    restored, metadata = restore_pose_for_evaluation(template, raw_path, restored_path)

    assert metadata["protocol_id"] == PROTOCOL_ID
    assert metadata["max_heavy_atom_coordinate_delta_angstrom"] == 0.0
    assert metadata["crystal_coordinates_used_for_mapping"] is False
    assert metadata["rigid_fit_performed"] is False
    assert metadata["minimization_performed"] is False
    assert metadata["template_formula"] == metadata["restored_formula"]
    assert _coordinate_multiset(restored) == _coordinate_multiset(raw)
    assert Chem.SanitizeMol(Chem.Mol(restored), catchErrors=True) == Chem.SanitizeFlags.SANITIZE_NONE


def _minimal_report() -> dict[str, object]:
    case = crossdock001.directed_case_specs()[0]
    normalization = {
        "protocol_id": PROTOCOL_ID,
        "method": "starting-conformer chemistry + exact docked heavy-atom coordinates",
        "template_source": "starting_conformer.sdf",
        "predicted_coordinate_source": "pose_01.sdf",
        "crystal_coordinates_used_for_mapping": False,
        "rigid_fit_performed": False,
        "minimization_performed": False,
        "heavy_atoms": 20,
        "atom_mapping_predicted_to_template": list(range(20)),
        "max_heavy_atom_coordinate_delta_angstrom": 0.0,
        "template_connectivity_identity": "C",
        "predicted_connectivity_identity": "C",
        "template_formula": "C20H20",
        "restored_formula": "C20H20",
    }
    record = {
        "case": case,
        "result": {
            "case_id": case["case_id"],
            "status": "PASS",
            "pose_1_rmsd_angstrom": 1.5,
            "minimum_rmsd_angstrom": 1.5,
            "pose_count": 1,
            "vina_pose_1_score_kcal_mol": -7.0,
            "pose_1_success": True,
            "first_near_native_rank": 1,
            "first_loss": None,
        },
        "provenance": {
            "structural_identity": {"grid_hash": "a" * 64},
            "alignment": {"rmsd_angstrom": 0.5},
            "engines": {
                "vina": {"version": "AutoDock Vina v1.2.7"},
                "openbabel": {"version": "Open Babel 3.1.1"},
            },
            "preparation": {},
            "docking": {"protocol_id": crossdock001.PROTOCOL_ID},
        },
        "poses": [
            {
                "rank": 1,
                "score_kcal_mol": -7.0,
                "status": "PASS",
                "rmsd_angstrom": 1.5,
                "reference_heavy_atoms": 20,
                "predicted_heavy_atoms": 20,
                "reference_identity": "C",
                "predicted_identity": "C",
                "rmsd_le_2_angstrom": True,
                "pdbqt_sha256": "b" * 64,
                "representation_normalization": normalization,
            }
        ],
    }
    return {
        "benchmark_id": crossdock001.BENCHMARK_ID,
        "protocol_id": crossdock001.PROTOCOL_ID,
        "pose_representation_protocol_id": PROTOCOL_ID,
        "evaluator_protocol_id": "research-os.redocking.v1.2",
        "preflight": {"selection_manifest_hash": "c" * 64},
        "frozen_cases": [case],
        "records": [record],
        "summary": {
            "total_cases": 1,
            "evaluable_pose_1_cases": 1,
            "pose_1_rmsd_le_2_angstrom": {"count": 1, "denominator": 1, "fraction": 1.0},
            "any_returned_pose_rmsd_le_2_angstrom": {"count": 1, "denominator": 1, "fraction": 1.0},
            "pose_1_rmsd_mean_angstrom": 1.5,
            "pose_1_rmsd_median_angstrom": 1.5,
        },
    }


def test_scientific_hash_commits_to_representation_normalization() -> None:
    report = _minimal_report()
    first = scientific_result_hash(report)
    changed = deepcopy(report)
    changed["records"][0]["poses"][0]["representation_normalization"][
        "rigid_fit_performed"
    ] = True
    assert scientific_result_hash(changed) != first
