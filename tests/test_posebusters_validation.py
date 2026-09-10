from __future__ import annotations

from copy import deepcopy
import math

from research_os.docking.posebusters_validation import (
    build_case_record,
    classify_posebusters,
    scientific_result_hash,
    summarize_case_records,
)


def test_pb_plausible_excludes_only_rmsd_binary() -> None:
    values = {
        "sanitization": True,
        "bond_lengths": True,
        "minimum_distance_to_protein_protein": True,
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
        "protocol_id": "research-os.posebusters.redock.v1.0",
        "posebusters": {"version": "0.6.5", "config": "redock"},
        "source_benchmarks": [{"benchmark_id": "REDOCK-001", "scientific_result_hash": "abc"}],
        "endpoint_definition": {"pb_plausible": "all non-RMSD binaries"},
        "records": [
            {
                "benchmark_id": "REDOCK-001",
                "case_id": "RDK-001",
                "source_same_frame_pose_1_rmsd_angstrom": 0.5,
                "source_same_frame_rmsd_le_2_angstrom": True,
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
    assert scientific_result_hash(report) == scientific_result_hash(changed)


def test_scientific_hash_changes_when_binary_scientific_outcome_changes() -> None:
    report = {
        "protocol_id": "research-os.posebusters.redock.v1.0",
        "posebusters": {"version": "0.6.5", "config": "redock"},
        "source_benchmarks": [],
        "endpoint_definition": {},
        "records": [
            {
                "benchmark_id": "REDOCK-001",
                "case_id": "RDK-001",
                "source_same_frame_pose_1_rmsd_angstrom": 0.5,
                "source_same_frame_rmsd_le_2_angstrom": True,
                "posebusters_binary_results": {"chemistry": True},
                "pb_plausible": True,
                "pb_valid": True,
                "localized_and_pb_plausible": True,
            }
        ],
        "summary": {"total_poses": 1},
    }
    changed = deepcopy(report)
    changed["records"][0]["posebusters_binary_results"]["chemistry"] = False
    assert scientific_result_hash(report) != scientific_result_hash(changed)
