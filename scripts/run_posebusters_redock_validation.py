from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
from typing import Any

import rdkit
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors
from posebusters import PoseBusters, __version__ as posebusters_version

from research_os.docking import redocking as redocking_v11
from research_os.docking.posebusters_validation import (
    INVALIDATED_V10_RUN_ID,
    INVALIDATED_V10_SCIENTIFIC_RESULT_HASH,
    POSEBUSTERS_CONFIG,
    POSEBUSTERS_REDOCK_CONFIG_GIT_BLOB_SHA1,
    POSEBUSTERS_VERSION,
    PROTOCOL_ID,
    REDOCK_001_PROTOCOL_ID,
    REDOCK_001_SCIENTIFIC_RESULT_HASH,
    REDOCK_002_PROTOCOL_ID,
    REDOCK_002_SCIENTIFIC_RESULT_HASH,
    build_case_record,
    restore_docked_pose_chemistry,
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


def _validate_pose_files(case_dir: Path) -> tuple[Path, Path, Path, Path]:
    predicted = case_dir / "pose_01.sdf"
    template = case_dir / "starting_conformer.sdf"
    reference = case_dir / "native_reference.sdf"
    receptor = case_dir / "receptor_extracted.pdb"
    missing = [
        str(path)
        for path in (predicted, template, reference, receptor)
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(f"missing frozen PoseBusters inputs: {missing}")
    return predicted, template, reference, receptor


def _write_restored_pose(mol: Chem.Mol, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = Chem.SDWriter(str(destination))
    writer.write(mol)
    writer.close()
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"failed to write chemistry-restored audit pose: {destination}")


def _verify_template_matches_reference(template: Chem.Mol, reference: Chem.Mol) -> dict[str, Any]:
    template_graph = redocking_v11._connectivity_graph(template)
    reference_graph = redocking_v11._connectivity_graph(reference)
    template_identity = Chem.MolToSmiles(template_graph, canonical=True, isomericSmiles=False)
    reference_identity = Chem.MolToSmiles(reference_graph, canonical=True, isomericSmiles=False)
    if template_identity != reference_identity:
        raise RuntimeError("starting conformer chemistry does not match the frozen reference connectivity")

    # Both molecules were already parsed and sanitized by load_single_sdf. Formula
    # comparison must use that chemically meaningful state directly: manually
    # deleting explicit H atoms without restoring implicit-H state creates an
    # artificial hydrogen deficit and was the implementation defect in run 269.
    template_formula = rdMolDescriptors.CalcMolFormula(template)
    reference_formula = rdMolDescriptors.CalcMolFormula(reference)
    if template_formula != reference_formula:
        raise RuntimeError("starting conformer formula does not match the frozen reference ligand")
    return {
        "template_reference_connectivity_match": True,
        "template_reference_formula_match": True,
        "reference_formula": reference_formula,
    }


def run_validation(
    redock_001_dir: Path,
    redock_002_dir: Path,
    *,
    audit_output_dir: Path | None = None,
) -> dict[str, Any]:
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
            predicted_path, template_path, reference_path, receptor_path = _validate_pose_files(
                root / case_id
            )
            predicted = redocking_v11.load_single_sdf(predicted_path)
            template = redocking_v11.load_single_sdf(template_path)
            reference = redocking_v11.load_single_sdf(reference_path)
            template_check = _verify_template_matches_reference(template, reference)
            restored, restoration = restore_docked_pose_chemistry(template, predicted)
            restoration = {**restoration, **template_check}

            if audit_output_dir is not None:
                _write_restored_pose(
                    restored,
                    audit_output_dir / "chemistry-restored" / f"{case_id}-pose-01.sdf",
                )

            dataframe = buster.bust(
                restored,
                mol_true=reference_path,
                mol_cond=receptor_path,
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
                    representation_normalization=restoration,
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
            "pose_selection": "as-generated Vina rank-1 heavy-atom coordinates; no repair, minimization, fitting or reranking",
            "representation_normalization": "restore known pre-docking ligand chemistry from starting_conformer.sdf while copying docked heavy-atom coordinates exactly; stereochemistry reassigned from docked 3D coordinates",
        },
        "records": case_records,
        "summary": summary,
        "audit_history": {
            "invalidated_v1.0_run_id": INVALIDATED_V10_RUN_ID,
            "invalidated_v1.0_scientific_result_hash": INVALIDATED_V10_SCIENTIFIC_RESULT_HASH,
            "invalidation_reason": "direct PDBQT-to-SDF poses lost non-polar hydrogens/chemical representation, causing PoseBusters identity/radical failures unrelated to docked heavy-atom geometry",
        },
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
        description="Validate frozen REDOCK-001/002 pose-1 coordinates with PoseBusters 0.6.5."
    )
    parser.add_argument("--redock-001-dir", required=True, type=Path)
    parser.add_argument("--redock-002-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    report = run_validation(
        args.redock_001_dir,
        args.redock_002_dir,
        audit_output_dir=args.output.parent,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "summary": report["summary"],
                "scientific_result_hash": report["scientific_result_hash"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
