from __future__ import annotations

from copy import deepcopy

from research_os.docking import crossdock001
from research_os.docking.crossdock001_runner import (
    scientific_result_hash,
    summarize_crossdock,
)


def _record(case_id: str, rmsd: float, minimum: float, first_rank: int | None) -> dict[str, object]:
    case = next(case for case in crossdock001.directed_case_specs() if case["case_id"] == case_id)
    return {
        "case": case,
        "result": {
            "case_id": case_id,
            "status": "PASS",
            "pose_1_rmsd_angstrom": rmsd,
            "minimum_rmsd_angstrom": minimum,
            "pose_count": 3,
            "vina_pose_1_score_kcal_mol": -7.5,
            "pose_1_success": rmsd <= 2.0,
            "first_near_native_rank": first_rank,
            "first_loss": None,
        },
        "provenance": {
            "structural_identity": {"grid_hash": "a" * 64},
            "alignment": {"rmsd_angstrom": 0.5},
            "engines": {
                "vina": {"version": "AutoDock Vina v1.2.7", "path": "/tmp/a"},
                "openbabel": {"version": "Open Babel 3.1.1", "path": "/tmp/b"},
            },
            "preparation": {
                "receptor": {
                    "returncode": 0,
                    "engine": "Open Babel",
                    "engine_version": "Open Babel 3.1.1",
                    "status": "SUPPORTED_AND_EXECUTED",
                    "output_sha256": "b" * 64,
                    "timed_out": False,
                    "protocol_id": "receptor",
                },
                "ligand": {
                    "returncode": 0,
                    "engine": "Open Babel",
                    "engine_version": "Open Babel 3.1.1",
                    "status": "SUPPORTED_AND_EXECUTED",
                    "output_sha256": "c" * 64,
                    "timed_out": False,
                    "protocol_id": "ligand",
                },
            },
            "docking": {
                "best_affinity_kcal_mol": -7.5,
                "returncode": 0,
                "engine": "AutoDock Vina",
                "engine_version": "AutoDock Vina v1.2.7",
                "status": "SUPPORTED_AND_EXECUTED",
                "receptor_sha256": "d" * 64,
                "ligand_sha256": "e" * 64,
                "output_sha256": "f" * 64,
                "grid_hash": "a" * 64,
                "target_id": "source->target",
                "protocol_id": crossdock001.PROTOCOL_ID,
                "timed_out": False,
            },
        },
        "poses": [
            {
                "rank": 1,
                "score_kcal_mol": -7.5,
                "status": "PASS",
                "rmsd_angstrom": rmsd,
                "reference_heavy_atoms": 20,
                "predicted_heavy_atoms": 20,
                "reference_identity": "C",
                "predicted_identity": "C",
                "rmsd_le_2_angstrom": rmsd <= 2.0,
                "pdbqt_sha256": "1" * 64,
            }
        ],
    }


def test_summary_keeps_scientific_failures_in_denominator() -> None:
    records = [
        _record("XDK-01-1", 1.0, 1.0, 1),
        _record("XDK-01-2", 4.0, 1.5, 2),
        _record("XDK-02-1", 5.0, 3.0, None),
    ]
    summary = summarize_crossdock(records)
    assert summary["total_cases"] == 3
    assert summary["evaluable_pose_1_cases"] == 3
    assert summary["pose_1_rmsd_le_2_angstrom"]["count"] == 1
    assert summary["pose_1_rmsd_le_2_angstrom"]["denominator"] == 3
    assert summary["any_returned_pose_rmsd_le_2_angstrom"]["count"] == 2
    assert summary["any_returned_pose_rmsd_le_2_angstrom"]["denominator"] == 3


def test_scientific_hash_ignores_host_environment_and_local_paths() -> None:
    record = _record("XDK-01-1", 1.25, 1.25, 1)
    report = {
        "benchmark_id": crossdock001.BENCHMARK_ID,
        "protocol_id": crossdock001.PROTOCOL_ID,
        "preflight": {"selection_manifest_hash": "9" * 64},
        "frozen_cases": [record["case"]],
        "records": [record],
        "summary": summarize_crossdock([record]),
        "environment": {"python": "3.12.1", "platform": "host-a"},
    }
    first = scientific_result_hash(report)
    changed = deepcopy(report)
    changed["environment"] = {"python": "3.12.9", "platform": "host-b"}
    changed["records"][0]["provenance"]["engines"]["vina"]["path"] = "/other/vina"
    changed["records"][0]["provenance"]["engines"]["openbabel"]["path"] = "/other/obabel"
    assert scientific_result_hash(changed) == first


def test_scientific_hash_changes_when_pose_rmsd_changes() -> None:
    record = _record("XDK-01-1", 1.25, 1.25, 1)
    report = {
        "benchmark_id": crossdock001.BENCHMARK_ID,
        "protocol_id": crossdock001.PROTOCOL_ID,
        "preflight": {"selection_manifest_hash": "9" * 64},
        "frozen_cases": [record["case"]],
        "records": [record],
        "summary": summarize_crossdock([record]),
        "environment": {},
    }
    first = scientific_result_hash(report)
    changed = deepcopy(report)
    changed["records"][0]["result"]["pose_1_rmsd_angstrom"] = 3.25
    changed["records"][0]["result"]["pose_1_success"] = False
    changed["records"][0]["poses"][0]["rmsd_angstrom"] = 3.25
    changed["records"][0]["poses"][0]["rmsd_le_2_angstrom"] = False
    changed["summary"] = summarize_crossdock(changed["records"])
    assert scientific_result_hash(changed) != first
