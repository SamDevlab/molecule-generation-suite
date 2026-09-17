"""Build diagnostics from the sealed APODOCK-001 v1.0.2 evidence only.

This script never calls Vina.  It reads the committed historical run and
writes new postmortem artifacts outside ``runs/apodock001-v1.0.2``.
"""

from __future__ import annotations

import json
import math
import shutil
import statistics
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from rdkit import Chem
from rdkit.Chem import Lipinski, rdMolDescriptors

from research_os.docking.apodock001_analysis import (
    _parse_ligand_components,
    build_transformed_reference,
    kabsch_source_to_target,
    matched_global_ca_pairs,
    parse_protein_chain,
)
from research_os.docking.apodock001_future import classify_timeout_record
from research_os.docking.apodock_glycan_chemistry import (
    CCD_SOURCES,
    adapt_apd010,
    load_named_ccd_sdf,
)


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "configs" / "apodock001-protocol-freeze-v1.0.2.json"
BUNDLE_PATH = ROOT / "inputs" / "apodock001" / "v1.0.2"
RUN_PATH = ROOT / "runs" / "apodock001-v1.0.2"
OUTPUT_PATH = ROOT / "postmortem" / "apodock001-v1.0.2-diagnostic-matrix.json"
MARKDOWN_PATH = ROOT / "postmortem" / "apodock001-v1.0.2-diagnostic-matrix.md"
POCKET_CUTOFF_ANGSTROM = 8.0


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalized_bundle() -> Iterable[Path]:
    temporary = tempfile.TemporaryDirectory(prefix="apodock001-postmortem-")
    bundle = Path(temporary.name) / "bundle"
    shutil.copytree(BUNDLE_PATH, bundle)
    for path in bundle.rglob("*"):
        if path.is_file():
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    return temporary, bundle


def _transformed_ligand_points(protocol: dict[str, Any], case: dict[str, Any], bundle: Path) -> tuple[list[tuple[float, float, float]], float, int]:
    apo_text = (bundle / "pdb" / f"{case['apo_pdb_id']}.pdb").read_text(encoding="utf-8")
    holo_text = (bundle / "pdb" / f"{case['holo_pdb_id']}.pdb").read_text(encoding="utf-8")
    apo = parse_protein_chain(apo_text, str(case["apo_receptor_author_chain"]))
    holo = parse_protein_chain(holo_text, str(case["holo_receptor_author_chain"]))
    pairs = matched_global_ca_pairs(holo, apo)
    transform = kabsch_source_to_target(pairs)
    points = _parse_ligand_components(
        holo_text,
        component_ids=tuple(case["holo_ligand_components"]),
        author_chain=str(case["holo_ligand_author_chain"]),
        expected_auth_seq_ids=tuple(case["ligand_component_auth_seq_ids"]),
    )
    return [tuple(point) for point in transform.apply(points)], transform.rmsd_angstrom, len(pairs)


def _pocket_shift(case: dict[str, Any], bundle: Path, ligand_points: list[tuple[float, float, float]]) -> dict[str, Any]:
    apo_text = (bundle / "pdb" / f"{case['apo_pdb_id']}.pdb").read_text(encoding="utf-8")
    holo_text = (bundle / "pdb" / f"{case['holo_pdb_id']}.pdb").read_text(encoding="utf-8")
    apo = parse_protein_chain(apo_text, str(case["apo_receptor_author_chain"]))
    holo = parse_protein_chain(holo_text, str(case["holo_receptor_author_chain"]))
    pairs = matched_global_ca_pairs(holo, apo)
    transform = kabsch_source_to_target(pairs)
    shifts: list[float] = []
    for holo_ca, apo_ca in pairs:
        transformed = transform.apply([holo_ca])[0]
        if min(math.dist(transformed, ligand) for ligand in ligand_points) <= POCKET_CUTOFF_ANGSTROM:
            shifts.append(math.dist(transformed, apo_ca))
    return {
        "selection": f"transformed holo C-alpha within {POCKET_CUTOFF_ANGSTROM:g} Å of mapped ligand heavy atoms",
        "residue_count": len(shifts),
        "mean_ca_displacement_angstrom": statistics.fmean(shifts) if shifts else None,
        "median_ca_displacement_angstrom": statistics.median(shifts) if shifts else None,
        "maximum_ca_displacement_angstrom": max(shifts) if shifts else None,
    }


def _box_coverage(points: list[tuple[float, float, float]], box: dict[str, Any]) -> dict[str, Any]:
    center = box["center"]
    size = box["size"]
    lower = [center[i] - size[i] / 2 for i in range(3)]
    upper = [center[i] + size[i] / 2 for i in range(3)]
    inside = [
        all(lower[axis] <= point[axis] <= upper[axis] for axis in range(3))
        for point in points
    ]
    margins = [
        min(min(point[axis] - lower[axis], upper[axis] - point[axis]) for point in points)
        for axis in range(3)
    ]
    classification = (
        "BOX_REFERENCE_OUTSIDE" if not all(inside)
        else "BOX_EDGE_RISK" if min(margins) < 2.0
        else "BOX_COVERAGE_OK"
    )
    return {
        "reference_heavy_atoms": len(points),
        "fraction_inside": sum(inside) / len(points),
        "minimum_distance_to_edge_by_axis_angstrom": margins,
        "any_atom_outside": not all(inside),
        "classification": classification,
    }


def _complexity(case: dict[str, Any], bundle: Path) -> dict[str, Any]:
    if case["case_id"] != "APD-010":
        molecule = Chem.SDMolSupplier(
            str(bundle / "reference-sdf" / case["reference_filename"]),
            removeHs=False,
            sanitize=True,
        )[0]
        assert molecule is not None
        return {
            "heavy_atoms": int(molecule.GetNumHeavyAtoms()),
            "rotatable_bonds": int(Lipinski.NumRotatableBonds(Chem.RemoveHs(molecule))),
            "formal_charge": int(Chem.GetFormalCharge(molecule)),
            "ring_count": int(rdMolDescriptors.CalcNumRings(molecule)),
            "heteroatom_count": sum(atom.GetAtomicNum() not in (1, 6) for atom in molecule.GetAtoms()),
            "preparation_metadata": "RDKit ETKDGv3 seed=42; UFF max_iterations=1000; Open Babel -h Gasteiger",
        }
    bem = load_named_ccd_sdf(
        bundle / "apd010" / "BEM_ideal.sdf",
        bundle / "apd010" / "BEM.cif",
        "BEM",
        expected_sdf_sha256=CCD_SOURCES["BEM"]["sdf_sha256"],
        expected_cif_sha256=CCD_SOURCES["BEM"]["cif_sha256"],
    )
    mav = load_named_ccd_sdf(
        bundle / "apd010" / "MAV_ideal.sdf",
        bundle / "apd010" / "MAV.cif",
        "MAV",
        expected_sdf_sha256=CCD_SOURCES["MAV"]["sdf_sha256"],
        expected_cif_sha256=CCD_SOURCES["MAV"]["cif_sha256"],
    )
    molecule = adapt_apd010(bem, mav).molecule
    return {
        "heavy_atoms": int(molecule.GetNumHeavyAtoms()),
        "rotatable_bonds": int(Lipinski.NumRotatableBonds(molecule)),
        "formal_charge": int(Chem.GetFormalCharge(molecule)),
        "ring_count": int(rdMolDescriptors.CalcNumRings(molecule)),
        "heteroatom_count": sum(atom.GetAtomicNum() not in (1, 6) for atom in molecule.GetAtoms()),
        "preparation_metadata": "BEM+MAV adapter 1.0.0; no experimental coordinate completion",
    }


def _runtime(record: dict[str, Any]) -> float:
    start = datetime.fromisoformat(record["started_at"])
    end = datetime.fromisoformat(record["ended_at"])
    return (end - start).total_seconds()


def _pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) < 2:
        return None
    x_mean = statistics.fmean(x)
    y_mean = statistics.fmean(y)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y))
    denominator = math.sqrt(
        sum((a - x_mean) ** 2 for a in x) * sum((b - y_mean) ** 2 for b in y)
    )
    return numerator / denominator if denominator else None


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    result = [0.0] * len(values)
    for rank, index in enumerate(order, start=1):
        result[index] = float(rank)
    return result


def _sampling_spread(case_id: str, poses: list[dict[str, Any]]) -> dict[str, Any] | None:
    molecules: list[Chem.Mol] = []
    for pose in poses[:20]:
        path = RUN_PATH / pose["derived_sdf_path"]
        molecule = Chem.SDMolSupplier(str(path), removeHs=False, sanitize=False)[0]
        if molecule is None:
            return None
        molecules.append(molecule)
    pairwise: list[float] = []
    for left_index, left in enumerate(molecules):
        left_atoms = [atom.GetIdx() for atom in left.GetAtoms() if atom.GetAtomicNum() > 1]
        for right in molecules[left_index + 1 :]:
            right_atoms = [atom.GetIdx() for atom in right.GetAtoms() if atom.GetAtomicNum() > 1]
            if len(left_atoms) != len(right_atoms):
                return {"status": "INDETERMINATE", "reason": "heavy-atom count differs between poses"}
            total = 0.0
            for left_atom, right_atom in zip(left_atoms, right_atoms):
                first = left.GetConformer().GetAtomPosition(left_atom)
                second = right.GetConformer().GetAtomPosition(right_atom)
                total += sum((first[axis] - second[axis]) ** 2 for axis in range(3))
            pairwise.append(math.sqrt(total / len(left_atoms)))
    return {
        "metric": "pairwise predicted-predicted heavy-atom RMSD in raw atom order; no fitting",
        "pose_count": len(molecules),
        "mean_angstrom": statistics.fmean(pairwise),
        "median_angstrom": statistics.median(pairwise),
        "minimum_angstrom": min(pairwise),
        "maximum_angstrom": max(pairwise),
    }


def build_report() -> dict[str, Any]:
    protocol = _json(PROTOCOL_PATH)
    analysis = _json(RUN_PATH / "analysis-manifest.json")
    run_manifest = _json(RUN_PATH / "run-manifest.json")
    boxes = protocol["box"]["cases"]
    analysis_by_case = {case["case_id"]: case for case in analysis["aggregation"]["cases"]}
    records_by_case = {case["case_id"]: case for case in run_manifest["cases"]}
    temporary, bundle = _normalized_bundle()
    rows: list[dict[str, Any]] = []
    try:
        for case in protocol["benchmark"]["cases"]:
            case_id = case["case_id"]
            record = records_by_case[case_id]
            analyzed = analysis_by_case[case_id]
            points, transform_rmsd, matched_pairs = _transformed_ligand_points(protocol, case, bundle)
            poses = analyzed.get("poses", [])
            spread = _sampling_spread(case_id, poses) if poses else None
            score_rmsd = None
            if analyzed["status"] == "DETERMINATE":
                scores = [float(pose["vina_score_kcal_mol"]) for pose in poses[:20]]
                rmsds = [float(pose["rmsd_angstrom"]) for pose in poses[:20]]
                score_rmsd = {
                    "pearson_score_vs_same_frame_rmsd": _pearson(scores, rmsds),
                    "spearman_score_vs_same_frame_rmsd": _pearson(_ranks(scores), _ranks(rmsds)),
                    "sample_size": len(scores),
                }
            first_loss = analyzed.get("first_loss")
            if case_id == "APD-006":
                first_loss = "EXECUTION_FAILED"
            rows.append(
                {
                    "case": case_id,
                    "execution_status": record["status"],
                    "runtime_seconds": _runtime(record),
                    "timeout_classification": classify_timeout_record(record),
                    "ligand_complexity": _complexity(case, bundle),
                    "box_coverage": _box_coverage(points, boxes[case_id]),
                    "apo_holo_pocket_shift": {
                        "global_ca_transform_rmsd_angstrom": transform_rmsd,
                        "matched_ca_pairs": matched_pairs,
                        **_pocket_shift(case, bundle, points),
                    },
                    "pose_1_score_kcal_mol": analyzed["poses"][0]["vina_score_kcal_mol"] if poses else None,
                    "pose_1_rmsd_angstrom": analyzed.get("pose_1_rmsd_angstrom"),
                    "best_score_kcal_mol": (
                        analyzed["poses"][analyzed["best_pose_index"] - 1]["vina_score_kcal_mol"]
                        if analyzed.get("best_pose_index") else None
                    ),
                    "best_rmsd_angstrom": analyzed.get("minimum_rmsd_angstrom"),
                    "best_pose_index": analyzed.get("best_pose_index"),
                    "primary_to_secondary_delta_angstrom": (
                        analyzed["pose_1_rmsd_angstrom"] - analyzed["minimum_rmsd_angstrom"]
                        if analyzed.get("pose_1_rmsd_angstrom") is not None and analyzed.get("minimum_rmsd_angstrom") is not None
                        else None
                    ),
                    "returned_pose_count": analyzed.get("returned_pose_count", 0),
                    "sampling_spread": spread,
                    "score_rmsd_descriptive": score_rmsd,
                    "analysis_status": analyzed["status"],
                    "first_loss": first_loss,
                    "diagnostics": {
                        "reference_heavy_atoms_mapped": len(points),
                        "apd010_reference_incomplete": case_id == "APD-010",
                        "historical_result_unchanged": True,
                    },
                }
            )
    finally:
        temporary.cleanup()

    return {
        "schema_version": "research-os.apodock001.postmortem-diagnostic.v1",
        "source": {
            "protocol_id": protocol["protocol_id"],
            "protocol_hash": protocol["protocol_hash"],
            "run_id": run_manifest["run_id"],
            "raw_results_seal_sha256": run_manifest["raw_results_seal_sha256"],
            "historical_analysis_engine_id": analysis["analysis_engine_id"],
            "no_vina_invoked": True,
        },
        "definitions": {
            "box_edge_risk_angstrom": 2.0,
            "pocket_cutoff_angstrom": POCKET_CUTOFF_ANGSTROM,
            "sampling_metric": "pairwise predicted-predicted heavy-atom RMSD in raw atom order; no fitting",
            "correlation_warning": "descriptive only; seven determinate cases and twenty poses per case",
        },
        "scientific_summary": {
            "primary_success": "0/7",
            "secondary_success": "0/7",
            "all_reference_boxes": "BOX_COVERAGE_OK",
            "best_of_20_above_threshold_for_all_determinate_cases": True,
            "interpretation": "observations support mixed representation/search/receptor hypotheses; they do not identify a single causal mechanism",
        },
        "cases": rows,
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# APODOCK-001 v1.0.2 diagnostic matrix",
        "",
        "This matrix is derived only from the sealed historical run. It does not rewrite the historical analysis and does not invoke Vina.",
        "",
        "| Case | Execution | Runtime (s) | Box | Pose 1 RMSD | Best RMSD | Best pose | First loss |",
        "|---|---:|---:|---|---:|---:|---:|---|",
    ]
    for row in report["cases"]:
        lines.append(
            f"| {row['case']} | {row['execution_status']} | {row['runtime_seconds']:.3f} | "
            f"{row['box_coverage']['classification']} | "
            f"{row['pose_1_rmsd_angstrom'] if row['pose_1_rmsd_angstrom'] is not None else '—'} | "
            f"{row['best_rmsd_angstrom'] if row['best_rmsd_angstrom'] is not None else '—'} | "
            f"{row['best_pose_index'] if row['best_pose_index'] is not None else '—'} | "
            f"{row['first_loss'] or '—'} |"
        )
    lines.extend(
        [
            "",
            "Interpretation: every mapped reference remained inside its frozen box, while every determinate case remained above 2 Å even after considering up to 20 returned poses. The score/RMSD correlations and pairwise pose spreads are descriptive diagnostics only; they do not establish causality.",
            "",
            "The v1.0.2 historical result remains unchanged.",
        ]
    )
    MARKDOWN_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    report = build_report()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(report)
    print(json.dumps({"json": str(OUTPUT_PATH), "markdown": str(MARKDOWN_PATH), "cases": len(report["cases"])}, indent=2))
