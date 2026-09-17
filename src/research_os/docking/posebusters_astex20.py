from __future__ import annotations

from typing import Any, Mapping

from research_os.docking.astex20 import FROZEN_PROSPECTIVE_CASES
from research_os.docking.posebusters_validation import (
    POSEBUSTERS_CONFIG,
    POSEBUSTERS_REDOCK_CONFIG_GIT_BLOB_SHA1,
    POSEBUSTERS_VERSION,
)
from research_os.docking.redocking_v12_identity import (
    scientific_result_hash as redock_scientific_result_hash,
)


BENCHMARK_ID = "PB-002"
PROTOCOL_ID = "research-os.posebusters.astex20.v1.0"
SOURCE_BENCHMARK_ID = "REDOCK-003"
SOURCE_PROTOCOL_ID = "research-os.redocking.astex20.v1.0"
SOURCE_EVALUATOR_PROTOCOL_ID = "research-os.redocking.v1.2"
SOURCE_SCIENTIFIC_RESULT_HASH = "e4e4693f890b86327fac16b547966fe64862045d1562c4340dcc3d7d4a06b762"
SOURCE_SUMMARY_HASH = "7fff66446032e26e4fa77d4c348a5cc5de499495025fcbf979f0e5124a316fd8"
SOURCE_RUN_ID = 34546751594
SOURCE_ARTIFACT_ID = 10179660428
SOURCE_ARTIFACT_ZIP_SHA256 = "fb0dadb67186eb2899b4c79f0a0a67683a16783cf834c587d43cdac076a98b7f"
SOURCE_RESULT_FILENAME = "redocking-astex20-result-v1.0.json"
EXPECTED_SOURCE_LOCALIZED = 8
EXPECTED_SOURCE_TOTAL = 15
EXPECTED_CASE_IDS = tuple(case.case_id for case in FROZEN_PROSPECTIVE_CASES)


def verify_source_report(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Fail closed unless input is exactly the sealed REDOCK-003 scientific result."""

    if report.get("benchmark_id") != SOURCE_BENCHMARK_ID:
        raise RuntimeError(f"source benchmark mismatch: {report.get('benchmark_id')!r}")
    if report.get("protocol_id") != SOURCE_PROTOCOL_ID:
        raise RuntimeError(f"source protocol mismatch: {report.get('protocol_id')!r}")
    if report.get("evaluator_protocol_id") != SOURCE_EVALUATOR_PROTOCOL_ID:
        raise RuntimeError(
            f"source evaluator protocol mismatch: {report.get('evaluator_protocol_id')!r}"
        )
    if report.get("scientific_result_hash") != SOURCE_SCIENTIFIC_RESULT_HASH:
        raise RuntimeError(
            "source scientific identity mismatch: "
            f"{report.get('scientific_result_hash')!r}"
        )

    recomputed_hash = redock_scientific_result_hash(dict(report))
    if recomputed_hash != SOURCE_SCIENTIFIC_RESULT_HASH:
        raise RuntimeError(
            "source scientific content hash mismatch: "
            f"expected {SOURCE_SCIENTIFIC_RESULT_HASH}, got {recomputed_hash}"
        )

    records = report.get("records")
    if not isinstance(records, list) or len(records) != EXPECTED_SOURCE_TOTAL:
        raise RuntimeError(
            f"source must contain exactly {EXPECTED_SOURCE_TOTAL} frozen records"
        )

    case_ids: list[str] = []
    normalized_records: list[dict[str, Any]] = []
    for raw_record in records:
        if not isinstance(raw_record, Mapping):
            raise RuntimeError("source record is not an object")
        record = dict(raw_record)
        result = record.get("result")
        if not isinstance(result, Mapping):
            raise RuntimeError("source record is missing result object")
        case_id = str(result.get("case_id", ""))
        case_ids.append(case_id)
        normalized_records.append(record)

    if tuple(case_ids) != EXPECTED_CASE_IDS:
        raise RuntimeError(
            f"source case identity/order mismatch: expected {EXPECTED_CASE_IDS!r}, got {tuple(case_ids)!r}"
        )

    summary = report.get("summary")
    if not isinstance(summary, Mapping):
        raise RuntimeError("source summary is missing")
    criterion = summary.get("pose_1_rmsd_le_2_angstrom")
    if not isinstance(criterion, Mapping):
        raise RuntimeError("source summary is missing pose-1 <=2 Å criterion")
    if int(criterion.get("count", -1)) != EXPECTED_SOURCE_LOCALIZED:
        raise RuntimeError("source localization count mismatch")
    if int(criterion.get("denominator", -1)) != EXPECTED_SOURCE_TOTAL:
        raise RuntimeError("source localization denominator mismatch")

    return normalized_records


def source_benchmark_identity() -> dict[str, Any]:
    return {
        "benchmark_id": SOURCE_BENCHMARK_ID,
        "protocol_id": SOURCE_PROTOCOL_ID,
        "evaluator_protocol_id": SOURCE_EVALUATOR_PROTOCOL_ID,
        "scientific_result_hash": SOURCE_SCIENTIFIC_RESULT_HASH,
        "summary_hash": SOURCE_SUMMARY_HASH,
        "case_count": EXPECTED_SOURCE_TOTAL,
    }


def source_evidence_identity() -> dict[str, Any]:
    """Archive provenance; intentionally audit-only, outside scientific hash payload."""

    return {
        "run_id": SOURCE_RUN_ID,
        "artifact_id": SOURCE_ARTIFACT_ID,
        "artifact_zip_sha256": SOURCE_ARTIFACT_ZIP_SHA256,
        "result_filename": SOURCE_RESULT_FILENAME,
    }


def posebusters_identity() -> dict[str, Any]:
    return {
        "version": POSEBUSTERS_VERSION,
        "config": POSEBUSTERS_CONFIG,
        "config_git_blob_sha1": POSEBUSTERS_REDOCK_CONFIG_GIT_BLOB_SHA1,
        "max_workers": 0,
        "full_report": False,
    }


def endpoint_definition() -> dict[str, str]:
    return {
        "source_localization": "sealed REDOCK-003 same-frame symmetry-aware pose-1 heavy-atom RMSD <= 2 Å",
        "pb_valid": "all official PoseBusters redock binary outputs pass, including its RMSD binary",
        "pb_plausible": "all official PoseBusters redock binary outputs except the RMSD binary pass",
        "combined": "source localization passes AND pb_plausible passes",
        "pose_selection": "sealed REDOCK-003 Vina rank-1 heavy-atom coordinates; no repair, minimization, fitting or reranking",
        "representation_normalization": "restore known pre-docking ligand chemistry from starting_conformer.sdf while copying docked heavy-atom coordinates exactly; stereochemistry reassigned from docked 3D coordinates",
    }
