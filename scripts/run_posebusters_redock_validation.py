from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
from typing import Any

import rdkit
from posebusters import PoseBusters, __version__ as posebusters_version

from research_os.docking.posebusters_validation import (
    POSEBUSTERS_CONFIG,
    POSEBUSTERS_REDOCK_CONFIG_GIT_BLOB_SHA1,
    POSEBUSTERS_VERSION,
    PROTOCOL_ID,
    REDOCK_001_PROTOCOL_ID,
    REDOCK_001_SCIENTIFIC_RESULT_HASH,
    REDOCK_002_PROTOCOL_ID,
    REDOCK_002_SCIENTIFIC_RESULT_HASH,
    build_case_record,
    scientific_result_hash,
    summarize_case_records,
)


SOURCE_SPECS = (
    {
        "benchmark_id": "REDOCK-001",
        "result_filename": "redocking-result-v1.2.json",
        "expected_protocol_id": REDOCK_001_PROTOCOL_ID,
        "expected_scientific_result_hash": REDOCK_001_SCIENTIFIC_RESULT_HASH,
        "case_prefix": "RDK-",
    },
    {
        "benchmark_id": "REDOCK-002",
        "result_filename": "redocking-holdout-result-v1.0.json",
        "expected_protocol_id": REDOCK_002_PROTOCOL_ID,
        "expected_scientific_result_hash": REDOCK_002_SCIENTIFIC_RESULT_HASH,
        "case_prefix": "HLD-",
    },
)


def _read_and_verify_source(root: Path, spec: dict[str, str]) -> dict[str, Any]:
    result_path = root / spec["result_filename"]
    if not result_path.is_file():
        raise FileNotFoundError(result_path)
    report = json.loads(result_path.read_text(encoding="utf-8"))
    if report.get("protocol_id") != spec["expected_protocol_id"]:
        raise RuntimeError(
            f"{spec['benchmark_id']} protocol mismatch: {report.get('protocol_id')!r}"
        )
    if report.get("scientific_result_hash") != spec["expected_scientific_result_hash"]:
        raise RuntimeError(
            f"{spec['benchmark_id']} scientific identity mismatch: "
            f"{report.get('scientific_result_hash')!r}"
        )
    records = report.get("records")
    if not isinstance(records, list) or len(records) != 5:
        raise RuntimeError(f"{spec['benchmark_id']} must contain exactly five frozen records")
    return report


def _source_pose_1_rmsd(record: dict[str, Any]) -> float | None:
    result = record.get("result") or {}
    value = result.get("pose_1_rmsd_angstrom")
    return float(value) if value is not None else None


def _validate_pose_files(case_dir: Path) -> tuple[Path, Path, Path]:
    predicted = case_dir / "pose_01.sdf"
    reference = case_dir / "native_reference.sdf"
    receptor = case_dir / "receptor_extracted.pdb"
    missing = [str(path) for path in (predicted, reference, receptor) if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing frozen PoseBusters inputs: {missing}")
    return predicted, reference, receptor


def run_validation(redock_001_dir: Path, redock_002_dir: Path) -> dict[str, Any]:
    if posebusters_version != POSEBUSTERS_VERSION:
        raise RuntimeError(
            f"PoseBusters version mismatch: expected {POSEBUSTERS_VERSION}, got {posebusters_version}"
        )

    roots = {
        "REDOCK-001": redock_001_dir,
        "REDOCK-002": redock_002_dir,
    }
    buster = PoseBusters(config=POSEBUSTERS_CONFIG, max_workers=0)
    case_records: list[dict[str, Any]] = []
    source_benchmarks: list[dict[str, Any]] = []

    for spec in SOURCE_SPECS:
        benchmark_id = spec["benchmark_id"]
        root = roots[benchmark_id]
        source_report = _read_and_verify_source(root, spec)
        source_benchmarks.append(
            {
                "benchmark_id": benchmark_id,
                "protocol_id": spec["expected_protocol_id"],
                "scientific_result_hash": spec["expected_scientific_result_hash"],
            }
        )

        for source_record in source_report["records"]:
            result = source_record.get("result") or {}
            case_id = str(result.get("case_id", ""))
            if not case_id.startswith(spec["case_prefix"]):
                raise RuntimeError(f"unexpected case id in {benchmark_id}: {case_id!r}")
            predicted, reference, receptor = _validate_pose_files(root / case_id)
            dataframe = buster.bust(
                predicted,
                mol_true=reference,
                mol_cond=receptor,
                full_report=False,
            )
            if len(dataframe.index) != 1:
                raise RuntimeError(
                    f"PoseBusters returned {len(dataframe.index)} rows for {benchmark_id}/{case_id}"
                )
            row = dataframe.iloc[0].to_dict()
            case_records.append(
                build_case_record(
                    benchmark_id=benchmark_id,
                    case_id=case_id,
                    source_rmsd_angstrom=_source_pose_1_rmsd(source_record),
                    binary_results=row,
                )
            )

    case_records.sort(key=lambda record: (record["benchmark_id"], record["case_id"]))
    summary = summarize_case_records(case_records)
    if summary["total_poses"] != 10:
        raise RuntimeError("PoseBusters validation must contain exactly ten frozen pose-1 inputs")
    if summary["source_same_frame_rmsd_le_2_angstrom"]["count"] != 7:
        raise RuntimeError(
            "frozen source localization identity mismatch: expected 7/10 pose-1 RMSD <= 2 Å"
        )

    report: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID,
        "posebusters": {
            "version": POSEBUSTERS_VERSION,
            "config": POSEBUSTERS_CONFIG,
            "config_git_blob_sha1": POSEBUSTERS_REDOCK_CONFIG_GIT_BLOB_SHA1,
            "max_workers": 0,
            "full_report": False,
        },
        "source_benchmarks": source_benchmarks,
        "endpoint_definition": {
            "source_localization": "Research OS same-frame symmetry-aware pose-1 heavy-atom RMSD <= 2 Å",
            "pb_valid": "all official PoseBusters redock binary outputs pass, including its RMSD binary",
            "pb_plausible": "all official PoseBusters redock binary outputs except the RMSD binary pass",
            "combined": "source localization passes AND pb_plausible passes",
            "pose_selection": "as-generated Vina rank-1 pose; no repair, minimization or reranking",
        },
        "records": case_records,
        "summary": summary,
        "environment": {
            "python": platform.python_version(),
            "rdkit": rdkit.__version__,
            "posebusters": posebusters_version,
            "redock_001_dir": str(redock_001_dir),
            "redock_002_dir": str(redock_002_dir),
        },
    }
    report["scientific_result_hash"] = scientific_result_hash(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate frozen REDOCK-001/002 pose-1 outputs with PoseBusters 0.6.5."
    )
    parser.add_argument("--redock-001-dir", required=True, type=Path)
    parser.add_argument("--redock-002-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    report = run_validation(args.redock_001_dir, args.redock_002_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps({"summary": report["summary"], "scientific_result_hash": report["scientific_result_hash"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
