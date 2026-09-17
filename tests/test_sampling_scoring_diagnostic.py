from __future__ import annotations

import copy
from pathlib import Path

import pytest

from research_os.docking.sampling_scoring_diagnostic import (
    SOURCE_INPUT_SHA256,
    analyze_sampling_scoring,
    load_sealed_input,
)


SNAPSHOT = Path(__file__).resolve().parents[1] / "validation" / "rank002-sampling-scoring-input-v1.0.json"


def _case(source: dict, case_id: str) -> dict:
    return next(item for item in source["cases"] if item["case_id"] == case_id)


def test_sealed_snapshot_reproduces_expected_failure_modes() -> None:
    payload = load_sealed_input(SNAPSHOT)
    result = analyze_sampling_scoring(payload)

    assert result["source_input_sha256"] == SOURCE_INPUT_SHA256
    assert result["diagnostic_hash"] == "e9bd4c6d3dd6ce88381cc85edf4cb2f74782b67d172b75659c7178bd0b86852d"

    redock, crossdock = result["sources"]
    assert redock["benchmark_id"] == "REDOCK-003"
    assert redock["classification_counts"] == {
        "RANK1_SUCCESS": 8,
        "RANKING_MISS": 4,
        "POSE_SET_MISS": 3,
    }
    assert crossdock["benchmark_id"] == "CROSSDOCK-001"
    assert crossdock["classification_counts"] == {
        "RANK1_SUCCESS": 3,
        "RANKING_MISS": 2,
        "POSE_SET_MISS": 5,
    }


def test_ranking_miss_records_rank_and_score_penalty() -> None:
    result = analyze_sampling_scoring(load_sealed_input(SNAPSHOT))
    redock, crossdock = result["sources"]

    atx006 = _case(redock, "ATX-006")
    assert atx006["classification"] == "RANKING_MISS"
    assert atx006["first_near_native_rank"] == 5
    assert atx006["near_native_score_penalty_vs_rank1_kcal_mol"] == pytest.approx(0.678)

    xdk042 = _case(crossdock, "XDK-04-2")
    assert xdk042["classification"] == "RANKING_MISS"
    assert xdk042["first_near_native_rank"] == 4
    assert xdk042["near_native_score_penalty_vs_rank1_kcal_mol"] == pytest.approx(0.648)

    pooled = result["pooled_ranking_miss_descriptive_only"]
    assert pooled["count"] == 6
    assert pooled["all_penalties_positive"] is True
    assert pooled["near_native_score_penalty_vs_rank1_kcal_mol"]["mean"] == pytest.approx(
        0.583166666667
    )


def test_cross_cohort_comparison_is_descriptive_and_kept_separate() -> None:
    result = analyze_sampling_scoring(load_sealed_input(SNAPSHOT))
    comparison = result["descriptive_cross_cohort_comparison"]

    assert comparison["pose_set_miss_fraction"]["REDOCK-003"] == pytest.approx(0.2)
    assert comparison["pose_set_miss_fraction"]["CROSSDOCK-001"] == pytest.approx(0.5)
    assert comparison["pose_set_miss_fraction"]["crossdock_minus_redock"] == pytest.approx(0.3)
    assert "descriptive" in comparison["note"].lower()
    assert "causal" in comparison["note"].lower()


def test_pose_set_miss_does_not_claim_unique_search_failure() -> None:
    result = analyze_sampling_scoring(load_sealed_input(SNAPSHOT))
    assert "does not identify a unique cause" in result["interpretation"]
    assert "rigid-receptor mismatch" in result["interpretation"]


def test_rejects_modified_source_identity() -> None:
    payload = load_sealed_input(SNAPSHOT)
    changed = copy.deepcopy(payload)
    changed["sources"][1]["scientific_result_hash"] = "0" * 64

    with pytest.raises(ValueError, match="sealed artifact"):
        analyze_sampling_scoring(changed)


def test_rejects_inconsistent_near_native_fields() -> None:
    payload = load_sealed_input(SNAPSHOT)
    changed = copy.deepcopy(payload)
    changed["sources"][0]["cases"][2]["best_returned_rmsd_angstrom"] = 1.5

    with pytest.raises(ValueError, match="missing first near-native"):
        analyze_sampling_scoring(changed)


def test_file_hash_blocks_snapshot_tampering(tmp_path: Path) -> None:
    data = SNAPSHOT.read_text(encoding="utf-8").replace('"ATX-001"', '"ATX-X01"', 1)
    tampered = tmp_path / "tampered.json"
    tampered.write_text(data, encoding="utf-8")

    with pytest.raises(ValueError, match="file hash"):
        load_sealed_input(tampered)
