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
from research_os.docking.posebusters_astex20 import (
    BENCHMARK_ID,
    EXPECTED_SOURCE_LOCALIZED,
    EXPECTED_SOURCE_TOTAL,
    POSEBUSTERS_CONFIG,
    POSEBUSTERS_VERSION,
    PROTOCOL_ID,
    SOURCE_RESULT_FILENAME,
    endpoint_definition,
    posebusters_identity,
    source_benchmark_identity,
    source_evidence_identity,
    verify_source_report,
)
from research_os.docking.posebusters_validation import (
    build_case_record,
    restore_docked_pose_chemistry,
    scientific_result_hash,
    summarize_case_records,
)


def _load_source(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result_path = root / SOURCE_RESULT_FILENAME
    if not result_path.is_file():
        raise FileNotFoundError(result_path)
    report = json.loads(result_path.read_text(encoding="utf-8"))
    records = verify_source_report(report)
    return report, records


def _source_pose_1_rmsd(record: dict[str, Any]) -> float | None:
    result = record.get("result") or {}
    value = result.get("pose_1_rmsd_angstrom")
    return float(value) if value is not None else None


def _validate_pose_files(case_dir: Path) -> tuple[Path, Path, Path, Path]:
    predicted = case_dir / "pose_01.sdf"
    template = case_dir / "starting_conformer.sdf"
    reference = case_dir / "native_reference.sdf"
    receptor = case_dir / "receptor_extracted.pdb"
    missing = [str(path) for path in (predicted, template, reference, receptor) if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing sealed PoseBusters inputs: {missing}")
    return predicted, template, reference, receptor


def _verify_template_matches_reference(template: Chem.Mol, reference: Chem.Mol) -> dict[str, Any]:
    template_graph = redocking_v11._connectivity_graph(template)
    reference_graph = redocking_v11._connectivity_graph(reference)
    template_identity = Chem.MolToSmiles(template_graph, canonical=True, isomericSmiles=False)
    reference_identity = Chem.MolToSmiles(reference_graph, canonical=True, isomericSmiles=False)
    if template_identity != reference_identity:
        raise RuntimeError("starting conformer chemistry does not match sealed reference connectivity")

    template_formula = rdMolDescriptors.CalcMolFormula(template)
    reference_formula = rdMolDescriptors.CalcMolFormula(reference)
    if template_formula != reference_formula:
        raise RuntimeError("starting conformer formula does not match sealed reference ligand")
    return {
        "template_reference_connectivity_match": True,
        "template_reference_formula_match": True,
        "reference_formula": reference_formula,
    }


def _write_restored_pose(mol: Chem.Mol, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = Chem.SDWriter(str(destination))
    writer.write(mol)
    writer.close()
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"failed to write chemistry-restored audit pose: {destination}")


def run_validation(
    source_dir: Path,
    *,
    audit_output_dir: Path | None = None,
) -> dict[str, Any]:
    if posebusters_version != POSEBUSTERS_VERSION:
        raise RuntimeError(
            f"PoseBusters version mismatch: expected {POSEBUSTERS_VERSION}, got {posebusters_version}"
        )

    _, source_records = _load_source(source_dir)
    buster = PoseBusters(config=POSEBUSTERS_CONFIG, max_workers=0)
    case_records: list[dict[str, Any]] = []

    for source_record in source_records:
        result = source_record.get("result") or {}
        case_id = str(result.get("case_id", ""))
        predicted_path, template_path, reference_path, receptor_path = _validate_pose_files(
            source_dir / case_id
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
            raise RuntimeError(f"PoseBusters returned {len(dataframe.index)} rows for {case_id}")
        row = dataframe.iloc[0].to_dict()
        case_records.append(
            build_case_record(
                benchmark_id="REDOCK-003",
                case_id=case_id,
                source_rmsd_angstrom=_source_pose_1_rmsd(source_record),
                binary_results=row,
                representation_normalization=restoration,
            )
        )

    case_records.sort(key=lambda record: record["case_id"])
    summary = summarize_case_records(case_records)
    if summary["total_poses"] != EXPECTED_SOURCE_TOTAL:
        raise RuntimeError("PB-002 must contain exactly fifteen sealed rank-1 poses")
    if summary["source_same_frame_rmsd_le_2_angstrom"]["count"] != EXPECTED_SOURCE_LOCALIZED:
        raise RuntimeError("sealed source localization identity mismatch")

    report: dict[str, Any] = {
        "benchmark_id": BENCHMARK_ID,
        "protocol_id": PROTOCOL_ID,
        "posebusters": posebusters_identity(),
        "source_benchmarks": [source_benchmark_identity()],
        "source_evidence": source_evidence_identity(),
        "endpoint_definition": endpoint_definition(),
        "records": case_records,
        "summary": summary,
        "environment": {
            "python": platform.python_version(),
            "rdkit": rdkit.__version__,
            "posebusters": posebusters_version,
            "source_dir": str(source_dir),
        },
    }
    report["scientific_result_hash"] = scientific_result_hash(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the 15 sealed REDOCK-003 rank-1 poses with PoseBusters 0.6.5."
    )
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    report = run_validation(args.source_dir, audit_output_dir=args.output.parent)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps({"summary": report["summary"], "scientific_result_hash": report["scientific_result_hash"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
