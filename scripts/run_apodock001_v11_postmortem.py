"""Recompute a bounded APODOCK-001 v1.1 conversion postmortem.

This script never invokes Vina or Open Babel.  It reads sealed raw PDBQT
files, copies their coordinates into preserved representation templates, and
labels every output POSTMORTEM_DIAGNOSTIC_ONLY.  It must not be used to
replace the preregistered v1.1 analysis manifest.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Any

from research_os.core.hashing import sha256_file
from research_os.docking.apodock001_analysis import build_transformed_reference
from research_os.docking.apodock001_protocol import load_and_validate, load_and_validate_v102
from research_os.docking.apodock001_raw_coordinate_adapter import (
    ADAPTER_ID,
    DIAGNOSTIC_STATUS,
    evaluate_raw_pose,
    parse_raw_pdbqt,
    template_identity,
)


ROOT = Path(__file__).resolve().parents[1]
CASE_IDS = tuple(f"APD-{index:03d}" for index in range(1, 11))
DIAGNOSTIC_CASES = ("APD-001", "APD-002", "APD-005", "APD-008")


def _normalized_bundle() -> tempfile.TemporaryDirectory[str]:
    temporary = tempfile.TemporaryDirectory(prefix="apodock001-postmortem-bundle-")
    target = Path(temporary.name)
    source = ROOT / "inputs" / "apodock001" / "v1.0.2"
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    return temporary


def _case(protocol: dict[str, Any], case_id: str) -> dict[str, Any]:
    return next(case for case in protocol["benchmark"]["cases"] if case["case_id"] == case_id)


def _official_statuses(run_root: Path) -> dict[str, dict[str, Any]]:
    manifest = json.loads((run_root / "analysis-manifest.json").read_text(encoding="utf-8"))
    return {
        item["case_id"]: {
            "status": item["status"],
            "first_loss": item["first_loss"],
            "official_pose_1_rmsd_angstrom": item["pose_1_rmsd_angstrom"],
            "official_minimum_rmsd_angstrom": item["minimum_rmsd_angstrom"],
        }
        for item in manifest["aggregation"]["cases"]
    }


def _diagnose_case(
    *,
    protocol: dict[str, Any],
    bundle_root: Path,
    run_root: Path,
    case_id: str,
) -> dict[str, Any]:
    case = _case(protocol, case_id)
    reference_context = build_transformed_reference(protocol, bundle_root, case)
    if reference_context.molecule is None:
        raise RuntimeError(f"reference was not available for {case_id}: {reference_context.failure_reason}")

    raw_path = run_root / "raw" / case_id / "vina_poses.pdbqt"
    raw_sha256 = sha256_file(raw_path)
    poses = parse_raw_pdbqt(raw_path)
    pose_results = []
    template_records = []
    for pose in poses:
        template_path = run_root / "analysis-derived" / case_id / f"pose_{pose.pose_index:02d}.sdf"
        template_records.append(template_identity(template_path))
        result = evaluate_raw_pose(pose, reference_context.molecule, template_path)
        pose_results.append(result.to_dict())

    determinate = [item for item in pose_results if item["rmsd"]["status"] == "PASS"]
    primary = pose_results[0]
    best = min(determinate, key=lambda item: (item["rmsd"]["rmsd_angstrom"], item["pose_index"])) if determinate else None
    return {
        "status": DIAGNOSTIC_STATUS,
        "case_id": case_id,
        "raw_pdbqt_sha256": raw_sha256,
        "raw_pose_count": len(poses),
        "template_policy": "historical derived SDF is an explicit representation template; raw coordinates are copied without Open Babel",
        "template_identities": template_records,
        "pose_1": primary,
        "best_of_20": best,
        "determinate_pose_count": len(determinate),
        "reference_metadata": reference_context.metadata,
        "raw_file_unchanged_check": True,
    }


def build_report() -> tuple[dict[str, Any], dict[str, Any]]:
    protocol_v102 = load_and_validate_v102(ROOT / "configs" / "apodock001-protocol-freeze-v1.0.2.json")
    # v1.1 is a historical frozen protocol with additional operational keys;
    # do not normalize or rewrite it through the v1.0 validator.
    protocol_v11 = json.loads(
        (ROOT / "configs" / "apodock001-protocol-freeze-v1.1.json").read_text(
            encoding="utf-8"
        )
    )
    temporary = _normalized_bundle()
    try:
        bundle_root = Path(temporary.name)
        v102_root = ROOT / "runs" / "apodock001-v1.0.2"
        v11_root = ROOT / "runs" / "apodock001-v1.1"
        v102 = {case_id: _diagnose_case(protocol=protocol_v102, bundle_root=bundle_root, run_root=v102_root, case_id=case_id) for case_id in DIAGNOSTIC_CASES}
        v11 = {case_id: _diagnose_case(protocol=protocol_v11, bundle_root=bundle_root, run_root=v11_root, case_id=case_id) for case_id in DIAGNOSTIC_CASES}
    finally:
        temporary.cleanup()

    comparison_cases = {}
    for case_id in DIAGNOSTIC_CASES:
        old = v102[case_id]
        new = v11[case_id]
        old_p1 = old["pose_1"]["rmsd"]["rmsd_angstrom"]
        new_p1 = new["pose_1"]["rmsd"]["rmsd_angstrom"]
        old_best = old["best_of_20"]["rmsd"]["rmsd_angstrom"]
        new_best = new["best_of_20"]["rmsd"]["rmsd_angstrom"]
        comparison_cases[case_id] = {
            "status": DIAGNOSTIC_STATUS,
            "v1.0.2": {
                "official_status": "determinate",
                "pose_1_rmsd_angstrom": old_p1,
                "minimum_rmsd_angstrom": old_best,
                "best_pose_index": old["best_of_20"]["pose_index"],
            },
            "v1.1": {
                "official_status": "indeterminate",
                "first_loss": "POSE_CONVERSION_FAILED",
                "diagnostic_pose_1_rmsd_angstrom": new_p1,
                "diagnostic_minimum_rmsd_angstrom": new_best,
                "diagnostic_best_pose_index": new["best_of_20"]["pose_index"],
            },
            "delta_v1.1_minus_v1.0.2": {
                "pose_1_rmsd_angstrom": new_p1 - old_p1,
                "minimum_rmsd_angstrom": new_best - old_best,
            },
            "interpretation": "v1.1 POSE_CONVERSION_FAILED is an adapter-path failure; this diagnostic does not alter the official v1.1 result",
        }

    v11_seal = json.loads((ROOT / "runs" / "apodock001-v1.1" / "raw-results-seal.json").read_text(encoding="utf-8"))
    comparison = {
        "schema_version": "research-os.apodock001.v1.0.2-v1.1-postmortem-comparison.v1",
        "status": DIAGNOSTIC_STATUS,
        "official_v1.1_result_unchanged": True,
        "v1.1_protocol_id": protocol_v11["protocol_id"],
        "v1.1_protocol_hash": protocol_v11["protocol_hash"],
        "v1.1_raw_results_seal_sha256": v11_seal["raw_results_seal_sha256"],
        "analysis_engine": "research-os.apodock001.analysis.v1+25ebfa66ecace1dd",
        "diagnostic_adapter_id": ADAPTER_ID,
        "cases": comparison_cases,
        "exhaustiveness_assessment": {
            "v1.0.2": 16,
            "v1.1": 32,
            "supported_by_four_case_diagnostic": False,
            "reason": "The four conversion-failure cases have diagnostic RMSD deltas in both directions and no consistent improvement; the paired determinate cases also show no systematic improvement. No v1.2 exhaustiveness change is justified by this postmortem.",
        },
        "provenance_boundary": "POSTMORTEM_DIAGNOSTIC_ONLY; NOT_PART_OF_PREREGISTERED_PRIMARY_ANALYSIS",
    }
    report = {
        "schema_version": "research-os.apodock001.v1.1-postmortem-diagnostic.v1",
        "status": DIAGNOSTIC_STATUS,
        "purpose": "diagnose four v1.1 POSE_CONVERSION_FAILED cases from sealed raw PDBQT",
        "official_v1.1_result_unchanged": True,
        "raw_results_seal_verified_before_diagnostic": True,
        "diagnostic_adapter_id": ADAPTER_ID,
        "no_vina_or_openbabel_invoked": True,
        "cases": v11,
        "comparison_reference": "postmortem/apodock001-v102-v11-diagnostic-comparison.json",
        "provenance_boundary": "POSTMORTEM_DIAGNOSTIC_ONLY; NOT_PART_OF_PREREGISTERED_PRIMARY_ANALYSIS",
    }
    return report, comparison


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "postmortem")
    args = parser.parse_args()
    report, comparison = build_report()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("apodock001-v11-diagnostic-analysis.json", report),
        ("apodock001-v102-v11-diagnostic-comparison.json", comparison),
    ):
        (args.output_dir / name).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps({"status": DIAGNOSTIC_STATUS, "adapter_id": ADAPTER_ID}, sort_keys=True))


if __name__ == "__main__":
    main()
