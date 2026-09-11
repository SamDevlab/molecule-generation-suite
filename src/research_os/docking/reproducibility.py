from __future__ import annotations

import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable

from research_os.core.hashing import sha256_json


DIAGNOSTIC_ID = "research-os.docking.reproducibility.v1"
DEFAULT_SUCCESS_THRESHOLD_ANGSTROM = 2.0


def _records_by_case(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = report.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("report must contain a non-empty records list")
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("each record must be an object")
        result = record.get("result")
        if not isinstance(result, dict):
            raise ValueError("each record must contain a result object")
        case_id = result.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("each result must contain a non-empty case_id")
        if case_id in indexed:
            raise ValueError(f"duplicate case_id {case_id!r}")
        indexed[case_id] = record
    return indexed


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite numeric value {value!r}")
    return number


def _primary_success(result: dict[str, Any], threshold: float) -> bool | None:
    if "pose_1_success" in result and result["pose_1_success"] is not None:
        return bool(result["pose_1_success"])
    rmsd = _float_or_none(result.get("pose_1_rmsd_angstrom"))
    if rmsd is None:
        return None
    return rmsd <= threshold


def _secondary_success(result: dict[str, Any], threshold: float) -> bool | None:
    first_rank = result.get("first_near_native_rank")
    if first_rank is not None:
        return True
    minimum = _float_or_none(result.get("minimum_rmsd_angstrom"))
    if minimum is None:
        return None
    return minimum <= threshold


def _input_identity(record: dict[str, Any]) -> dict[str, Any]:
    provenance = record.get("provenance") or {}
    preparation = provenance.get("preparation") or {}
    docking = provenance.get("docking") or {}
    structural = provenance.get("structural_identity")

    def prep_hash(name: str) -> Any:
        payload = preparation.get(name) or {}
        return payload.get("output_sha256")

    return {
        "structural_identity": structural,
        "receptor_pdbqt_sha256": docking.get("receptor_sha256") or prep_hash("receptor"),
        "ligand_pdbqt_sha256": docking.get("ligand_sha256") or prep_hash("ligand"),
        "grid_hash": docking.get("grid_hash") or (structural or {}).get("grid_hash"),
    }


def _all_equal(values: Iterable[Any]) -> bool:
    materialized = list(values)
    if not materialized:
        return True
    first = materialized[0]
    return all(value == first for value in materialized[1:])


def _numeric_summary(values: list[float | None]) -> dict[str, Any]:
    finite = [value for value in values if value is not None]
    if not finite:
        return {
            "values": values,
            "minimum": None,
            "maximum": None,
            "range": None,
            "mean": None,
        }
    minimum = min(finite)
    maximum = max(finite)
    return {
        "values": values,
        "minimum": minimum,
        "maximum": maximum,
        "range": maximum - minimum,
        "mean": statistics.fmean(finite),
    }


def diagnostic_payload(diagnostic: dict[str, Any]) -> dict[str, Any]:
    return {
        "diagnostic_id": diagnostic["diagnostic_id"],
        "benchmark_id": diagnostic["benchmark_id"],
        "protocol_ids": diagnostic["protocol_ids"],
        "success_threshold_angstrom": diagnostic["success_threshold_angstrom"],
        "replicate_count": diagnostic["replicate_count"],
        "replicates": diagnostic["replicates"],
        "primary_endpoint": diagnostic["primary_endpoint"],
        "secondary_endpoint": diagnostic["secondary_endpoint"],
        "input_identity": diagnostic["input_identity"],
        "cases": diagnostic["cases"],
    }


def analyze_replicates(
    reports: list[dict[str, Any]],
    *,
    success_threshold_angstrom: float = DEFAULT_SUCCESS_THRESHOLD_ANGSTROM,
) -> dict[str, Any]:
    if len(reports) < 2:
        raise ValueError("at least two reports are required")
    if success_threshold_angstrom <= 0 or not math.isfinite(success_threshold_angstrom):
        raise ValueError("success threshold must be a finite positive number")

    benchmark_ids = [report.get("benchmark_id") for report in reports]
    if not all(isinstance(value, str) and value for value in benchmark_ids):
        raise ValueError("every report must contain benchmark_id")
    if not _all_equal(benchmark_ids):
        raise ValueError("reports belong to different benchmarks")

    record_sets = [_records_by_case(report) for report in reports]
    case_ids = sorted(record_sets[0])
    for indexed in record_sets[1:]:
        if sorted(indexed) != case_ids:
            raise ValueError("replicates do not contain the same case set")

    protocol_ids = [
        str(
            report.get("docking_protocol_id")
            or report.get("protocol_id")
            or report.get("benchmark_id")
        )
        for report in reports
    ]
    representation_protocol_ids = [report.get("pose_representation_protocol_id") for report in reports]

    replicate_rows: list[dict[str, Any]] = []
    primary_counts: list[int] = []
    secondary_counts: list[int] = []
    for index, (report, indexed) in enumerate(zip(reports, record_sets), start=1):
        primary = [
            _primary_success(indexed[case_id]["result"], success_threshold_angstrom)
            for case_id in case_ids
        ]
        secondary = [
            _secondary_success(indexed[case_id]["result"], success_threshold_angstrom)
            for case_id in case_ids
        ]
        primary_count = sum(value is True for value in primary)
        secondary_count = sum(value is True for value in secondary)
        primary_counts.append(primary_count)
        secondary_counts.append(secondary_count)
        replicate_rows.append(
            {
                "replicate": index,
                "scientific_result_hash": report.get("scientific_result_hash"),
                "execution_hash": report.get("execution_hash"),
                "primary_success_count": primary_count,
                "secondary_success_count": secondary_count,
                "case_count": len(case_ids),
            }
        )

    case_rows: list[dict[str, Any]] = []
    unstable_primary_cases: list[str] = []
    unstable_secondary_cases: list[str] = []
    unstable_input_cases: list[str] = []
    for case_id in case_ids:
        records = [indexed[case_id] for indexed in record_sets]
        results = [record["result"] for record in records]
        primary_values = [
            _primary_success(result, success_threshold_angstrom) for result in results
        ]
        secondary_values = [
            _secondary_success(result, success_threshold_angstrom) for result in results
        ]
        input_identities = [_input_identity(record) for record in records]
        primary_stable = _all_equal(primary_values)
        secondary_stable = _all_equal(secondary_values)
        input_stable = _all_equal(input_identities)
        if not primary_stable:
            unstable_primary_cases.append(case_id)
        if not secondary_stable:
            unstable_secondary_cases.append(case_id)
        if not input_stable:
            unstable_input_cases.append(case_id)

        pose1_rmsds = [_float_or_none(result.get("pose_1_rmsd_angstrom")) for result in results]
        minimum_rmsds = [_float_or_none(result.get("minimum_rmsd_angstrom")) for result in results]
        pose_counts = [int(result.get("pose_count") or 0) for result in results]
        scores = [_float_or_none(result.get("vina_pose_1_score_kcal_mol")) for result in results]
        case_rows.append(
            {
                "case_id": case_id,
                "primary_success": primary_values,
                "primary_stable": primary_stable,
                "secondary_success": secondary_values,
                "secondary_stable": secondary_stable,
                "input_identity_stable": input_stable,
                "pose_1_rmsd_angstrom": _numeric_summary(pose1_rmsds),
                "minimum_rmsd_angstrom": _numeric_summary(minimum_rmsds),
                "pose_count": {
                    "values": pose_counts,
                    "minimum": min(pose_counts),
                    "maximum": max(pose_counts),
                    "range": max(pose_counts) - min(pose_counts),
                },
                "vina_pose_1_score_kcal_mol": _numeric_summary(scores),
            }
        )

    scientific_hashes = [report.get("scientific_result_hash") for report in reports]
    diagnostic: dict[str, Any] = {
        "diagnostic_id": DIAGNOSTIC_ID,
        "benchmark_id": benchmark_ids[0],
        "protocol_ids": {
            "docking": protocol_ids,
            "pose_representation": representation_protocol_ids,
        },
        "success_threshold_angstrom": success_threshold_angstrom,
        "replicate_count": len(reports),
        "replicates": replicate_rows,
        "primary_endpoint": {
            "success_counts": primary_counts,
            "stable_across_replicates": len(set(primary_counts)) == 1 and not unstable_primary_cases,
            "unstable_cases": unstable_primary_cases,
        },
        "secondary_endpoint": {
            "success_counts": secondary_counts,
            "stable_across_replicates": len(set(secondary_counts)) == 1 and not unstable_secondary_cases,
            "unstable_cases": unstable_secondary_cases,
        },
        "input_identity": {
            "stable_across_replicates": not unstable_input_cases,
            "unstable_cases": unstable_input_cases,
        },
        "scientific_result_hashes": scientific_hashes,
        "unique_scientific_result_hash_count": len(set(scientific_hashes)),
        "cases": case_rows,
    }
    diagnostic["diagnostic_hash"] = sha256_json(diagnostic_payload(diagnostic))
    return diagnostic


def load_reports(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in paths:
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{source}: report root must be an object")
        reports.append(payload)
    return reports
