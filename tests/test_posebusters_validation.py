from __future__ import annotations

from copy import deepcopy
import math

from rdkit import Chem
from rdkit.Chem import AllChem, rdMolDescriptors

from research_os.docking.posebusters_validation import (
    build_case_record,
    classify_posebusters,
    restore_docked_pose_chemistry,
    scientific_result_hash,
    summarize_case_records,
)


def test_pb_plausible_excludes_only_rmsd_binary() -> None:
    values = {
        "sanitization": True,
        "bond_lengths": True,
        "minimum_distance_to_protein": True,
        "rmsd_≤_2å": False,
    }
    classification = classify_posebusters(values)
    assert classification == {"pb_valid": False, "pb_plausible": True}


def test_physical_failure_fails_pb_plausible_even_when_rmsd_passes() -> None:
    values = {
        "sanitization": True,
        "bond_lengths": False,
        "rmsd_≤_2å": True,
    }
    classification = classify_posebusters(values)
    assert classification == {"pb_valid": False, "pb_plausible": False}


def test_missing_binary_result_fails_closed() -> None:
    values = {
        "sanitization": True,
        "bond_lengths": None,
        "rmsd_≤_2å": True,
    }
    classification = classify_posebusters(values)
    assert classification == {"pb_valid": False, "pb_plausible": False}


def test_build_case_record_normalizes_nan_and_combined_endpoint() -> None:
    record = build_case_record(
        benchmark_id="REDOCK-002",
        case_id="HLD-001",
        source_rmsd_angstrom=0.6179566327825927,
        binary_results={
            "sanitization": True,
            "optional": math.nan,
            "rmsd_≤_2å": True,
        },
    )
    assert record["source_same_frame_pose_1_rmsd_angstrom"] == 0.617956632783
    assert record["source_same_frame_rmsd_le_2_angstrom"] is True
    assert record["posebusters_binary_results"]["optional"] is None
    assert record["pb_plausible"] is False
    assert record["localized_and_pb_plausible"] is False


def test_restore_docked_pose_chemistry_restores_formula_without_moving_heavy_atoms() -> None:
    template = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    assert AllChem.EmbedMolecule(template, params) == 0

    predicted = Chem.RemoveHs(Chem.Mol(template))
    predicted = Chem.RenumberAtoms(predicted, [2, 1, 0])
    predicted_conf = predicted.GetConformer()
    for index in range(predicted.GetNumAtoms()):
        position = predicted_conf.GetAtomPosition(index)
        predicted_conf.SetAtomPosition(index, (position.x + 5.0, position.y - 2.0, position.z + 1.0))

    restored, metadata = restore_docked_pose_chemistry(template, predicted)
    mapping = metadata["atom_mapping_predicted_to_template"]
    restored_conf = restored.GetConformer()
    predicted_conf = predicted.GetConformer()
    for predicted_index, template_index in enumerate(mapping):
        predicted_position = predicted_conf.GetAtomPosition(predicted_index)
        restored_position = restored_conf.GetAtomPosition(template_index)
        assert restored_position.x == predicted_position.x
        assert restored_position.y == predicted_position.y
        assert restored_position.z == predicted_position.z

    assert metadata["max_heavy_atom_coordinate_delta_angstrom"] == 0.0
    assert metadata["crystal_coordinates_used_for_mapping"] is False
    assert metadata["rigid_fit_performed"] is False
    assert metadata["minimization_performed"] is False
    assert rdMolDescriptors.CalcMolFormula(restored) == rdMolDescriptors.CalcMolFormula(
        Chem.RemoveHs(template)
    )


def test_summary_keeps_source_localization_separate_from_plausibility() -> None:
    records = [
        build_case_record(
            benchmark_id="REDOCK-001",
            case_id="RDK-001",
            source_rmsd_angstrom=0.5,
            binary_results={"chemistry": True, "rmsd_≤_2å": True},
        ),
        build_case_record(
            benchmark_id="REDOCK-002",
            case_id="HLD-001",
            source_rmsd_angstrom=3.0,
            binary_results={"chemistry": True, "rmsd_≤_2å": False},
        ),
        build_case_record(
            benchmark_id="REDOCK-002",
            case_id="HLD-002",
            source_rmsd_angstrom=1.0,
            binary_results={"chemistry": False, "rmsd_≤_2å": True},
        ),
    ]
    summary = summarize_case_records(records)
    assert summary["source_same_frame_rmsd_le_2_angstrom"]["count"] == 2
    assert summary["pb_plausible"]["count"] == 2
    assert summary["pb_valid"]["count"] == 1
    assert summary["localized_and_pb_plausible"]["count"] == 1


def test_scientific_hash_ignores_audit_only_environment_and_paths() -> None:
    report = {
        "protocol_id": "research-os.posebusters.redock.v1.1",
        "posebusters": {"version": "0.6.5", "config": "redock"},
        "source_benchmarks": [{"benchmark_id": "REDOCK-001", "scientific_result_hash": "abc"}],
        "endpoint_definition": {"pb_plausible": "all non-RMSD binaries"},
        "records": [
            {
                "benchmark_id": "REDOCK-001",
                "case_id": "RDK-001",
                "source_same_frame_pose_1_rmsd_angstrom": 0.5,
                "source_same_frame_rmsd_le_2_angstrom": True,
                "representation_normalization": {"max_heavy_atom_coordinate_delta_angstrom": 0.0},
                "posebusters_binary_results": {"chemistry": True, "rmsd": True},
                "pb_plausible": True,
                "pb_valid": True,
                "localized_and_pb_plausible": True,
            }
        ],
        "summary": {"total_poses": 1},
        "environment": {"path": "/tmp/a", "runtime_seconds": 1.0},
    }
    changed = deepcopy(report)
    changed["environment"] = {"path": "C:/different", "runtime_seconds": 999.0}
    changed["stdout"] = "different"
    changed["audit_history"] = {"note": "audit-only field"}
    assert scientific_result_hash(report) == scientific_result_hash(changed)


def test_scientific_hash_changes_when_restoration_or_binary_outcome_changes() -> None:
    report = {
        "protocol_id": "research-os.posebusters.redock.v1.1",
        "posebusters": {"version": "0.6.5", "config": "redock"},
        "source_benchmarks": [],
        "endpoint_definition": {},
        "records": [
            {
                "benchmark_id": "REDOCK-001",
                "case_id": "RDK-001",
                "source_same_frame_pose_1_rmsd_angstrom": 0.5,
                "source_same_frame_rmsd_le_2_angstrom": True,
                "representation_normalization": {"atom_mapping_predicted_to_template": [0, 1]},
                "posebusters_binary_results": {"chemistry": True},
                "pb_plausible": True,
                "pb_valid": True,
                "localized_and_pb_plausible": True,
            }
        ],
        "summary": {"total_poses": 1},
    }
    changed_binary = deepcopy(report)
    changed_binary["records"][0]["posebusters_binary_results"]["chemistry"] = False
    assert scientific_result_hash(report) != scientific_result_hash(changed_binary)

    changed_mapping = deepcopy(report)
    changed_mapping["records"][0]["representation_normalization"]["atom_mapping_predicted_to_template"] = [1, 0]
    assert scientific_result_hash(report) != scientific_result_hash(changed_mapping)
