from __future__ import annotations

import copy
import json
import math
import statistics
from pathlib import Path
from typing import Any

from research_os.core.hashing import sha256_file, sha256_json


BENCHMARK_ID = "RANK-002"
PROTOCOL_ID = "research-os.docking.sampling-scoring-diagnostic.v1.0"
SCHEMA_VERSION = "research-os.rank002.input.v1"
SOURCE_INPUT_SHA256 = "3f256dada77e5eb030d5c281359b7a154bdb683a1d960047c9bfbc31349b5e9c"
RMSD_THRESHOLD_ANGSTROM = 2.0

EXPECTED_SOURCES = {
    "REDOCK-003": {
        "benchmark_id": "REDOCK-003",
        "cohort_role": "prospective Astex-20 redocking cohort",
        "run_id": 34546751594,
        "artifact_id": 10179660428,
        "artifact_zip_sha256": "fb0dadb67186eb2899b4c79f0a0a67683a16783cf834c587d43cdac076a98b7f",
        "scientific_result_hash": "e4e4693f890b86327fac16b547966fe64862045d1562c4340dcc3d7d4a06b762",
        "summary_hash": "7fff66446032e26e4fa77d4c348a5cc5de499495025fcbf979f0e5124a316fd8",
        "case_count": 15,
    },
    "CROSSDOCK-001": {
        "benchmark_id": "CROSSDOCK-001",
        "cohort_role": "prospective rigid holo-holo cross-docking cohort",
        "run_id": 34615447564,
        "artifact_id": 10271091364,
        "artifact_zip_sha256": "a5094acefffa7d52e30d887ef765d7524e728faff0beb9cf5eb6048caa663e91",
        "scientific_result_hash": "d1d5b980816837301c1fe70d2c0a397ba4a0e662bced7aa17bb118c61f2bff16",
        "case_count": 10,
    },
}


def _finite(value: object, *, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    return number


def _optional_finite(value: object, *, field: str) -> float | None:
    if value is None:
        return None
    return _finite(value, field=field)


def _validate_case(case: dict[str, Any], *, benchmark_id: str) -> None:
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError(f"{benchmark_id} case_id missing")
    pose_count = case.get("pose_count")
    if not isinstance(pose_count, int) or isinstance(pose_count, bool) or pose_count < 1:
        raise ValueError(f"{case_id} pose_count invalid")

    rank1_rmsd = _finite(case.get("rank1_rmsd_angstrom"), field=f"{case_id} rank1 RMSD")
    _finite(case.get("rank1_score_kcal_mol"), field=f"{case_id} rank1 score")
    best_rank = case.get("best_returned_rank")
    if not isinstance(best_rank, int) or isinstance(best_rank, bool) or not 1 <= best_rank <= pose_count:
        raise ValueError(f"{case_id} best returned rank invalid")
    best_rmsd = _finite(
        case.get("best_returned_rmsd_angstrom"), field=f"{case_id} best returned RMSD"
    )
    _finite(case.get("best_returned_score_kcal_mol"), field=f"{case_id} best returned score")
    if best_rmsd > rank1_rmsd + 1e-12:
        raise ValueError(f"{case_id} best returned RMSD cannot exceed rank1 RMSD")

    first_rank = case.get("first_near_native_rank")
    first_rmsd = _optional_finite(
        case.get("first_near_native_rmsd_angstrom"), field=f"{case_id} first near-native RMSD"
    )
    first_score = _optional_finite(
        case.get("first_near_native_score_kcal_mol"), field=f"{case_id} first near-native score"
    )
    if first_rank is None:
        if first_rmsd is not None or first_score is not None:
            raise ValueError(f"{case_id} near-native fields must all be null together")
        if best_rmsd <= RMSD_THRESHOLD_ANGSTROM:
            raise ValueError(f"{case_id} missing first near-native despite best RMSD <= threshold")
    else:
        if not isinstance(first_rank, int) or isinstance(first_rank, bool) or not 1 <= first_rank <= pose_count:
            raise ValueError(f"{case_id} first near-native rank invalid")
        if first_rmsd is None or first_score is None:
            raise ValueError(f"{case_id} near-native fields must all be present together")
        if first_rmsd > RMSD_THRESHOLD_ANGSTROM:
            raise ValueError(f"{case_id} first near-native RMSD exceeds threshold")
        if rank1_rmsd <= RMSD_THRESHOLD_ANGSTROM and first_rank != 1:
            raise ValueError(f"{case_id} rank1 success must have first near-native rank 1")
        if rank1_rmsd > RMSD_THRESHOLD_ANGSTROM and first_rank == 1:
            raise ValueError(f"{case_id} rank1 miss cannot have first near-native rank 1")


def _validate_source(source: dict[str, Any]) -> list[dict[str, Any]]:
    benchmark_id = source.get("benchmark_id")
    if benchmark_id not in EXPECTED_SOURCES:
        raise ValueError(f"unexpected RANK-002 source {benchmark_id!r}")
    expected = EXPECTED_SOURCES[benchmark_id]
    metadata = {key: source.get(key) for key in expected}
    if metadata != expected:
        raise ValueError(f"{benchmark_id} source identity does not match the sealed artifact")

    cases = source.get("cases")
    if not isinstance(cases, list) or len(cases) != expected["case_count"]:
        raise ValueError(f"{benchmark_id} case count changed")
    ids: list[str] = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError(f"{benchmark_id} case record must be a mapping")
        _validate_case(case, benchmark_id=benchmark_id)
        ids.append(case["case_id"])
    if len(set(ids)) != len(ids):
        raise ValueError(f"{benchmark_id} duplicate case_id")
    return cases


def _validate_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("RANK-002 input schema changed")
    if payload.get("criterion") != {
        "metric": "same-frame symmetry-aware heavy-atom RMSD",
        "threshold_angstrom": RMSD_THRESHOLD_ANGSTROM,
        "coordinate_fitting": False,
    }:
        raise ValueError("RANK-002 criterion changed")
    sources = payload.get("sources")
    if not isinstance(sources, list) or len(sources) != 2:
        raise ValueError("RANK-002 requires exactly two sealed sources")
    source_ids = [source.get("benchmark_id") for source in sources if isinstance(source, dict)]
    if source_ids != ["REDOCK-003", "CROSSDOCK-001"]:
        raise ValueError("RANK-002 source order or identity changed")
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("RANK-002 sources must be mappings")
        _validate_source(source)
    return sources


def load_sealed_input(path: str | Path) -> dict[str, Any]:
    source_path = Path(path)
    if sha256_file(source_path) != SOURCE_INPUT_SHA256:
        raise ValueError("RANK-002 input file hash does not match the sealed snapshot")
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("RANK-002 input must be a JSON object")
    _validate_payload(payload)
    return payload


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"values": [], "mean": None, "median": None, "minimum": None, "maximum": None}
    return {
        "values": values,
        "mean": round(statistics.fmean(values), 12),
        "median": round(statistics.median(values), 12),
        "minimum": min(values),
        "maximum": max(values),
    }


def _analyze_source(source: dict[str, Any]) -> dict[str, Any]:
    cases = _validate_source(source)
    rows: list[dict[str, Any]] = []
    ranking_ranks: list[int] = []
    ranking_penalties: list[float] = []

    for case in cases:
        rank1_rmsd = float(case["rank1_rmsd_angstrom"])
        first_rank = case["first_near_native_rank"]
        if rank1_rmsd <= RMSD_THRESHOLD_ANGSTROM:
            classification = "RANK1_SUCCESS"
            score_penalty = 0.0
        elif first_rank is not None:
            classification = "RANKING_MISS"
            score_penalty = round(
                float(case["first_near_native_score_kcal_mol"])
                - float(case["rank1_score_kcal_mol"]),
                12,
            )
            ranking_ranks.append(int(first_rank))
            ranking_penalties.append(score_penalty)
        else:
            classification = "POSE_SET_MISS"
            score_penalty = None

        rows.append(
            {
                "case_id": case["case_id"],
                "classification": classification,
                "pose_count": case["pose_count"],
                "rank1_rmsd_angstrom": rank1_rmsd,
                "rank1_score_kcal_mol": float(case["rank1_score_kcal_mol"]),
                "first_near_native_rank": first_rank,
                "first_near_native_rmsd_angstrom": case["first_near_native_rmsd_angstrom"],
                "first_near_native_score_kcal_mol": case["first_near_native_score_kcal_mol"],
                "near_native_score_penalty_vs_rank1_kcal_mol": score_penalty,
                "best_returned_rank": case["best_returned_rank"],
                "best_returned_rmsd_angstrom": case["best_returned_rmsd_angstrom"],
                "best_returned_score_kcal_mol": case["best_returned_score_kcal_mol"],
            }
        )

    count = len(rows)
    counts = {
        key: sum(row["classification"] == key for row in rows)
        for key in ("RANK1_SUCCESS", "RANKING_MISS", "POSE_SET_MISS")
    }
    any_near = counts["RANK1_SUCCESS"] + counts["RANKING_MISS"]
    return {
        "benchmark_id": source["benchmark_id"],
        "source_identity": copy.deepcopy(EXPECTED_SOURCES[source["benchmark_id"]]),
        "case_count": count,
        "classification_counts": counts,
        "classification_fractions": {key: counts[key] / count for key in counts},
        "any_returned_pose_le_2a": {
            "count": any_near,
            "denominator": count,
            "fraction": any_near / count,
        },
        "ranking_misses": {
            "count": len(ranking_ranks),
            "first_near_native_rank": {
                "values": ranking_ranks,
                "mean": statistics.fmean(ranking_ranks) if ranking_ranks else None,
                "median": statistics.median(ranking_ranks) if ranking_ranks else None,
            },
            "near_native_score_penalty_vs_rank1_kcal_mol": _stats(ranking_penalties),
            "all_penalties_positive": all(value > 0 for value in ranking_penalties),
        },
        "cases": rows,
    }


def analyze_sampling_scoring(
    payload: dict[str, Any], *, source_input_sha256: str = SOURCE_INPUT_SHA256
) -> dict[str, Any]:
    sources = _validate_payload(payload)
    analyzed = [_analyze_source(source) for source in sources]
    by_id = {item["benchmark_id"]: item for item in analyzed}
    redock = by_id["REDOCK-003"]
    crossdock = by_id["CROSSDOCK-001"]

    pooled_ranking_ranks = [
        rank
        for source in analyzed
        for rank in source["ranking_misses"]["first_near_native_rank"]["values"]
    ]
    pooled_penalties = [
        value
        for source in analyzed
        for value in source["ranking_misses"]["near_native_score_penalty_vs_rank1_kcal_mol"]["values"]
    ]

    result = {
        "benchmark_id": BENCHMARK_ID,
        "protocol_id": PROTOCOL_ID,
        "role": (
            "retrospective diagnostic over sealed REDOCK-003 and CROSSDOCK-001 artifacts; "
            "not a new prospective benchmark or independent holdout"
        ),
        "source_input_sha256": source_input_sha256,
        "criterion": copy.deepcopy(payload["criterion"]),
        "sources": analyzed,
        "descriptive_cross_cohort_comparison": {
            "note": (
                "The cohorts differ in receptor condition and case composition. Differences are descriptive "
                "and do not by themselves establish a causal effect of receptor conformation."
            ),
            "rank1_success_fraction": {
                "REDOCK-003": redock["classification_fractions"]["RANK1_SUCCESS"],
                "CROSSDOCK-001": crossdock["classification_fractions"]["RANK1_SUCCESS"],
                "crossdock_minus_redock": (
                    crossdock["classification_fractions"]["RANK1_SUCCESS"]
                    - redock["classification_fractions"]["RANK1_SUCCESS"]
                ),
            },
            "ranking_miss_fraction": {
                "REDOCK-003": redock["classification_fractions"]["RANKING_MISS"],
                "CROSSDOCK-001": crossdock["classification_fractions"]["RANKING_MISS"],
                "crossdock_minus_redock": (
                    crossdock["classification_fractions"]["RANKING_MISS"]
                    - redock["classification_fractions"]["RANKING_MISS"]
                ),
            },
            "pose_set_miss_fraction": {
                "REDOCK-003": redock["classification_fractions"]["POSE_SET_MISS"],
                "CROSSDOCK-001": crossdock["classification_fractions"]["POSE_SET_MISS"],
                "crossdock_minus_redock": (
                    crossdock["classification_fractions"]["POSE_SET_MISS"]
                    - redock["classification_fractions"]["POSE_SET_MISS"]
                ),
            },
        },
        "pooled_ranking_miss_descriptive_only": {
            "count": len(pooled_ranking_ranks),
            "first_near_native_rank": {
                "values": pooled_ranking_ranks,
                "mean": statistics.fmean(pooled_ranking_ranks) if pooled_ranking_ranks else None,
                "median": statistics.median(pooled_ranking_ranks) if pooled_ranking_ranks else None,
            },
            "near_native_score_penalty_vs_rank1_kcal_mol": _stats(pooled_penalties),
            "all_penalties_positive": all(value > 0 for value in pooled_penalties),
            "interpretation": (
                "A positive penalty means Vina assigned the first <=2 Å pose a numerically worse score "
                "than pose 1. These score differences are ranking diagnostics, not physical binding free energies."
            ),
        },
        "interpretation": (
            "RANKING_MISS means a <=2 Å pose existed in the returned pose set but was not ranked first. "
            "POSE_SET_MISS means no returned pose met the 2 Å criterion; it does not identify a unique cause "
            "and may reflect search, rigid-receptor mismatch, preparation, or other protocol limitations."
        ),
    }
    result["diagnostic_hash"] = sha256_json(result)
    return result
