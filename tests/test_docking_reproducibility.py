from __future__ import annotations

import pytest

from research_os.docking.reproducibility import analyze_replicates


def _record(
    case_id: str,
    *,
    pose1: float,
    minimum: float,
    pose_count: int,
    score: float,
    receptor_hash: str,
    ligand_hash: str,
    grid_hash: str,
) -> dict:
    return {
        "result": {
            "case_id": case_id,
            "status": "PASS",
            "pose_1_rmsd_angstrom": pose1,
            "minimum_rmsd_angstrom": minimum,
            "pose_count": pose_count,
            "vina_pose_1_score_kcal_mol": score,
            "pose_1_success": pose1 <= 2.0,
            "first_near_native_rank": 1 if pose1 <= 2.0 else (4 if minimum <= 2.0 else None),
        },
        "provenance": {
            "structural_identity": {"grid_hash": grid_hash},
            "docking": {
                "receptor_sha256": receptor_hash,
                "ligand_sha256": ligand_hash,
                "grid_hash": grid_hash,
            },
        },
    }


def _report(hash_value: str, *, variant: bool = False) -> dict:
    return {
        "benchmark_id": "CROSSDOCK-001",
        "docking_protocol_id": "research-os.crossdocking.rigid.v1.0",
        "pose_representation_protocol_id": "research-os.crossdocking.pose-representation.v1.1",
        "scientific_result_hash": hash_value,
        "execution_hash": f"exec-{hash_value}",
        "records": [
            _record(
                "XDK-A",
                pose1=1.0,
                minimum=0.8,
                pose_count=10,
                score=-7.0,
                receptor_hash="r-a",
                ligand_hash="l-a",
                grid_hash="g-a",
            ),
            _record(
                "XDK-B",
                pose1=3.5,
                minimum=1.9 if variant else 2.1,
                pose_count=12 if variant else 10,
                score=-8.1 if variant else -8.0,
                receptor_hash="r-b",
                ligand_hash="l-b",
                grid_hash="g-b",
            ),
        ],
    }


def test_detects_stable_primary_and_variable_secondary() -> None:
    first = _report("hash-a")
    second = _report("hash-b", variant=True)
    third = _report("hash-a")

    diagnostic = analyze_replicates([first, second, third])

    assert diagnostic["replicate_count"] == 3
    assert diagnostic["primary_endpoint"] == {
        "success_counts": [1, 1, 1],
        "stable_across_replicates": True,
        "unstable_cases": [],
    }
    assert diagnostic["secondary_endpoint"] == {
        "success_counts": [1, 2, 1],
        "stable_across_replicates": False,
        "unstable_cases": ["XDK-B"],
    }
    assert diagnostic["input_identity"]["stable_across_replicates"] is True
    assert diagnostic["unique_scientific_result_hash_count"] == 2
    case_b = next(case for case in diagnostic["cases"] if case["case_id"] == "XDK-B")
    assert case_b["primary_stable"] is True
    assert case_b["secondary_stable"] is False
    assert case_b["minimum_rmsd_angstrom"]["range"] == pytest.approx(0.2)
    assert case_b["pose_count"]["values"] == [10, 12, 10]
    assert isinstance(diagnostic["diagnostic_hash"], str)
    assert len(diagnostic["diagnostic_hash"]) == 64


def test_detects_input_identity_drift() -> None:
    first = _report("hash-a")
    second = _report("hash-a")
    second["records"][1]["provenance"]["docking"]["ligand_sha256"] = "changed"

    diagnostic = analyze_replicates([first, second])

    assert diagnostic["input_identity"] == {
        "stable_across_replicates": False,
        "unstable_cases": ["XDK-B"],
    }


def test_rejects_different_case_sets() -> None:
    first = _report("hash-a")
    second = _report("hash-b")
    second["records"].pop()

    with pytest.raises(ValueError, match="same case set"):
        analyze_replicates([first, second])


def test_requires_two_reports() -> None:
    with pytest.raises(ValueError, match="at least two"):
        analyze_replicates([_report("hash-a")])
