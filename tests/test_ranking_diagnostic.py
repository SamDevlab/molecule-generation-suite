from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from research_os.docking.ranking_diagnostic import (
    SOURCE_INPUT_SHA256,
    analyze_ranking,
    load_sealed_input,
)


FIXTURE = Path(__file__).parents[1] / "validation" / "rank001-astex20-input-v1.0.json"


def test_rank001_sealed_snapshot_identity_and_expected_diagnostic() -> None:
    payload = load_sealed_input(FIXTURE)
    report = analyze_ranking(payload)

    assert report["source_input_sha256"] == SOURCE_INPUT_SHA256
    assert report["top_k_recovery"] == {
        "1": {"count": 8, "denominator": 15, "fraction": 8 / 15},
        "3": {"count": 11, "denominator": 15, "fraction": 11 / 15},
        "5": {"count": 12, "denominator": 15, "fraction": 12 / 15},
        "10": {"count": 12, "denominator": 15, "fraction": 12 / 15},
    }
    assert report["any_returned_pose_le_2a"] == {
        "count": 12,
        "denominator": 15,
        "fraction": 12 / 15,
    }
    assert report["classification_counts"] == {
        "RANK1_SUCCESS": 8,
        "RANKING_FAILURE_RECOVERED": 4,
        "POSE_SET_MISS_NO_RETURNED_POSE_LE_2A": 3,
    }
    assert report["diagnostic_hash"] == (
        "36af521a178327b77e19a9bb2338637627312293d8ebddd7418f0b6c96a2b238"
    )


def test_rank001_recovered_rank1_failures_are_frozen() -> None:
    report = analyze_ranking(load_sealed_input(FIXTURE))
    by_id = {item["case_id"]: item for item in report["cases"]}

    assert by_id["ATX-006"]["first_pose_le_2a_rank"] == 5
    assert by_id["ATX-009"]["first_pose_le_2a_rank"] == 3
    assert by_id["ATX-012"]["first_pose_le_2a_rank"] == 2
    assert by_id["ATX-013"]["first_pose_le_2a_rank"] == 3
    assert report["recovered_rank1_failures"] == {
        "count": 4,
        "first_success_ranks": [5, 3, 2, 3],
        "mean_first_success_rank": 3.25,
        "median_first_success_rank": 3.0,
        "score_penalty_vs_rank1_kcal_mol": {
            "values": [0.678, 0.469, 0.144, 0.589],
            "mean": 0.47,
            "median": 0.529,
        },
    }


def test_rank001_three_cases_have_no_returned_pose_within_2a() -> None:
    report = analyze_ranking(load_sealed_input(FIXTURE))
    pose_set_misses = {
        item["case_id"]
        for item in report["cases"]
        if item["classification"] == "POSE_SET_MISS_NO_RETURNED_POSE_LE_2A"
    }
    assert pose_set_misses == {"ATX-003", "ATX-004", "ATX-014"}


def test_rank001_rejects_source_identity_change() -> None:
    payload = load_sealed_input(FIXTURE)
    changed = copy.deepcopy(payload)
    changed["source"]["run_id"] += 1
    with pytest.raises(ValueError, match="source identity"):
        analyze_ranking(changed)


def test_rank001_rejects_changed_criterion() -> None:
    payload = load_sealed_input(FIXTURE)
    changed = copy.deepcopy(payload)
    changed["criterion"]["threshold_angstrom"] = 2.1
    with pytest.raises(ValueError, match="criterion changed"):
        analyze_ranking(changed)


def test_rank001_rejects_mismatched_pose_arrays() -> None:
    payload = load_sealed_input(FIXTURE)
    changed = copy.deepcopy(payload)
    changed["cases"][0]["rmsd_angstrom"].pop()
    with pytest.raises(ValueError, match="score/RMSD arrays"):
        analyze_ranking(changed)


def test_rank001_file_hash_fails_closed(tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["cases"][0]["rmsd_angstrom"][0] += 0.001
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(raw, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="file hash"):
        load_sealed_input(changed)
