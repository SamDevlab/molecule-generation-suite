from __future__ import annotations

import copy
import json
import math
import statistics
from pathlib import Path
from typing import Any

from research_os.core.hashing import sha256_file, sha256_json


BENCHMARK_ID = "RANK-001"
PROTOCOL_ID = "research-os.ranking.astex20.v1.0"
SCHEMA_VERSION = "research-os.rank001.input.v1"
SOURCE_RUN_ID = 34546751594
SOURCE_ARTIFACT_ID = 10179660428
SOURCE_ARTIFACT_ZIP_SHA256 = "fb0dadb67186eb2899b4c79f0a0a67683a16783cf834c587d43cdac076a98b7f"
SOURCE_SCIENTIFIC_RESULT_HASH = "e4e4693f890b86327fac16b547966fe64862045d1562c4340dcc3d7d4a06b762"
SOURCE_SUMMARY_HASH = "7fff66446032e26e4fa77d4c348a5cc5de499495025fcbf979f0e5124a316fd8"
SOURCE_INPUT_SHA256 = "1f8a7fe04550003e79711918d0c30e1c42b3ddfae072b4dbab179263d01f262f"
RMSD_THRESHOLD_ANGSTROM = 2.0
EXPECTED_CASE_COUNT = 15
TOP_K = (1, 3, 5, 10)


def _finite_number(value: object, *, field: str) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{field} must be a finite number")
    return float(value)


def _validate_source(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("RANK-001 input schema changed")

    source = payload.get("source")
    if not isinstance(source, dict):
        raise ValueError("RANK-001 source metadata is missing")

    expected_source = {
        "benchmark_id": "REDOCK-003",
        "protocol_id": "research-os.redocking.astex20.v1.0",
        "evaluator_protocol_id": "research-os.redocking.v1.2",
        "run_id": SOURCE_RUN_ID,
        "artifact_id": SOURCE_ARTIFACT_ID,
        "artifact_zip_sha256": SOURCE_ARTIFACT_ZIP_SHA256,
        "scientific_result_hash": SOURCE_SCIENTIFIC_RESULT_HASH,
        "summary_hash": SOURCE_SUMMARY_HASH,
    }
    if source != expected_source:
        raise ValueError("RANK-001 source identity does not match sealed REDOCK-003 run 280")

    criterion = payload.get("criterion")
    if criterion != {
        "metric": "same-frame symmetry-aware heavy-atom RMSD",
        "threshold_angstrom": RMSD_THRESHOLD_ANGSTROM,
        "coordinate_fitting": False,
    }:
        raise ValueError("RANK-001 criterion changed")


def _validated_cases(payload: dict[str, Any]) -> list[dict[str, Any]]:
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != EXPECTED_CASE_COUNT:
        raise ValueError("RANK-001 requires exactly 15 sealed Astex cases")

    case_ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    if len(case_ids) != EXPECTED_CASE_COUNT or len(set(case_ids)) != EXPECTED_CASE_COUNT:
        raise ValueError("RANK-001 case ids must be present and unique")

    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("RANK-001 case records must be mappings")
        for field in ("case_id", "pdb_id", "ligand_id"):
            if not isinstance(case.get(field), str) or not case[field]:
                raise ValueError(f"RANK-001 case field {field} is missing")
        scores = case.get("scores_kcal_mol")
        rmsds = case.get("rmsd_angstrom")
        if not isinstance(scores, list) or not isinstance(rmsds, list):
            raise ValueError(f"{case['case_id']} pose arrays are malformed")
        if not scores or len(scores) != len(rmsds):
            raise ValueError(f"{case['case_id']} score/RMSD arrays must have equal nonzero length")
        for index, (score, rmsd) in enumerate(zip(scores, rmsds, strict=True), start=1):
            _finite_number(score, field=f"{case['case_id']} pose {index} score_kcal_mol")
            _finite_number(rmsd, field=f"{case['case_id']} pose {index} rmsd_angstrom")
    return cases


def load_sealed_input(path: str | Path) -> dict[str, Any]:
    input_path = Path(path)
    if sha256_file(input_path) != SOURCE_INPUT_SHA256:
        raise ValueError("RANK-001 input file hash does not match the sealed snapshot")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("RANK-001 input must be a JSON object")
    _validate_source(payload)
    _validated_cases(payload)
    return payload


def analyze_ranking(
    payload: dict[str, Any], *, source_input_sha256: str = SOURCE_INPUT_SHA256
) -> dict[str, Any]:
    _validate_source(payload)
    cases = _validated_cases(payload)

    case_results: list[dict[str, Any]] = []
    first_success_ranks: list[int] = []
    recovered_failure_ranks: list[int] = []
    recovered_score_penalties: list[float] = []

    for case in cases:
        scores = [float(value) for value in case["scores_kcal_mol"]]
        rmsds = [float(value) for value in case["rmsd_angstrom"]]
        first_success_rank = next(
            (index for index, rmsd in enumerate(rmsds, start=1) if rmsd <= RMSD_THRESHOLD_ANGSTROM),
            None,
        )

        if first_success_rank is None:
            classification = "POSE_SET_MISS_NO_RETURNED_POSE_LE_2A"
            score_penalty = None
        else:
            first_success_ranks.append(first_success_rank)
            if first_success_rank == 1:
                classification = "RANK1_SUCCESS"
                score_penalty = 0.0
            else:
                classification = "RANKING_FAILURE_RECOVERED"
                recovered_failure_ranks.append(first_success_rank)
                score_penalty = round(scores[first_success_rank - 1] - scores[0], 12)
                recovered_score_penalties.append(score_penalty)

        case_results.append(
            {
                "case_id": case["case_id"],
                "pdb_id": case["pdb_id"],
                "ligand_id": case["ligand_id"],
                "pose_count": len(rmsds),
                "classification": classification,
                "first_pose_le_2a_rank": first_success_rank,
                "rank1_rmsd_angstrom": rmsds[0],
                "minimum_returned_rmsd_angstrom": min(rmsds),
                "rank1_score_kcal_mol": scores[0],
                "first_pose_le_2a_score_penalty_kcal_mol": score_penalty,
            }
        )

    top_k = {}
    for k in TOP_K:
        count = sum(rank <= k for rank in first_success_ranks)
        top_k[str(k)] = {
            "count": count,
            "denominator": EXPECTED_CASE_COUNT,
            "fraction": count / EXPECTED_CASE_COUNT,
        }

    any_count = len(first_success_ranks)
    classification_counts = {
        "RANK1_SUCCESS": sum(item["classification"] == "RANK1_SUCCESS" for item in case_results),
        "RANKING_FAILURE_RECOVERED": sum(
            item["classification"] == "RANKING_FAILURE_RECOVERED" for item in case_results
        ),
        "POSE_SET_MISS_NO_RETURNED_POSE_LE_2A": sum(
            item["classification"] == "POSE_SET_MISS_NO_RETURNED_POSE_LE_2A"
            for item in case_results
        ),
    }

    diagnostic = {
        "benchmark_id": BENCHMARK_ID,
        "protocol_id": PROTOCOL_ID,
        "role": "retrospective diagnostic over sealed REDOCK-003 run 280; not an independent holdout",
        "source": copy.deepcopy(payload["source"]),
        "source_input_sha256": source_input_sha256,
        "criterion": copy.deepcopy(payload["criterion"]),
        "case_count": EXPECTED_CASE_COUNT,
        "top_k_recovery": top_k,
        "any_returned_pose_le_2a": {
            "count": any_count,
            "denominator": EXPECTED_CASE_COUNT,
            "fraction": any_count / EXPECTED_CASE_COUNT,
        },
        "classification_counts": classification_counts,
        "recovered_rank1_failures": {
            "count": len(recovered_failure_ranks),
            "first_success_ranks": recovered_failure_ranks,
            "mean_first_success_rank": (
                statistics.fmean(recovered_failure_ranks) if recovered_failure_ranks else None
            ),
            "median_first_success_rank": (
                statistics.median(recovered_failure_ranks) if recovered_failure_ranks else None
            ),
            "score_penalty_vs_rank1_kcal_mol": {
                "values": recovered_score_penalties,
                "mean": (
                    round(statistics.fmean(recovered_score_penalties), 12)
                    if recovered_score_penalties
                    else None
                ),
                "median": (
                    round(statistics.median(recovered_score_penalties), 12)
                    if recovered_score_penalties
                    else None
                ),
            },
        },
        "cases": case_results,
        "interpretation": (
            "This diagnostic separates whether a <=2 Å pose was returned from whether Vina ranked it first. "
            "It does not establish affinity, potency, biological activity, safety, efficacy, or independent "
            "generalization beyond the already-observed REDOCK-003 cohort."
        ),
    }
    diagnostic["diagnostic_hash"] = sha256_json(diagnostic)
    return diagnostic
