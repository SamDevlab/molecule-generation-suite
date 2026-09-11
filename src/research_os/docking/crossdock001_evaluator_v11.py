from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rdkit import Chem

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking import crossdock001
from research_os.docking import redocking as base
from research_os.docking import redocking_v12 as rmsd_evaluator
from research_os.docking.crossdock001_runner import (
    POSE_SUCCESS_THRESHOLD_ANGSTROM,
    run_frozen_crossdock001,
    summarize_crossdock,
)
from research_os.docking.posebusters_validation import restore_docked_pose_chemistry


PROTOCOL_ID = "research-os.crossdocking.pose-representation.v1.1"

# The first real CROSSDOCK-001 Vina execution is retained as audit evidence.
# Vina completed all ten frozen docking cases, but the direct PDBQT->SDF
# representation made XDK-05-1 chemically unsanitizable in RDKit, leaving only
# 9/10 evaluable pose-1 endpoints. No case, grid, Vina parameter, rank, or RMSD
# threshold is changed by v1.1; only known pre-docking ligand chemistry is
# restored around the exact docked heavy-atom coordinates for evaluation.
INVALIDATED_V10_RUN_ID = 34612986306
INVALIDATED_V10_SCIENTIFIC_RESULT_HASH = (
    "f7e9e77a6b375d14b05686de681478205b4e84bbcceafbfa8131de7814b09411"
)
INVALIDATED_V10_ARTIFACT_ID = 10269612880
INVALIDATED_V10_ARTIFACT_ZIP_SHA256 = (
    "4be2256cfeac8aa05d60cb1327587ba682faa90a27a405ada6b2cf0f9dd5cbd5"
)


def _normalize(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 12)
    if isinstance(value, dict):
        return {key: _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def load_single_unsanitized_pose(path: str | Path) -> Chem.Mol:
    """Load exactly one Open Babel pose without trusting its reconstructed chemistry."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    supplier = Chem.SDMolSupplier(str(source), removeHs=False, sanitize=False)
    molecules = [mol for mol in supplier if mol is not None]
    if len(molecules) != 1:
        raise ValueError(f"expected exactly one unsanitized pose in {source}, found {len(molecules)}")
    mol = molecules[0]
    if mol.GetNumConformers() != 1:
        raise ValueError("converted pose must contain exactly one conformer")
    return mol


def _write_restored_pose(mol: Chem.Mol, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = Chem.SDWriter(str(destination))
    writer.write(mol)
    writer.close()
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"failed to write chemistry-restored pose: {destination}")


def restore_pose_for_evaluation(
    template: Chem.Mol,
    predicted_path: str | Path,
    restored_path: str | Path,
) -> tuple[Chem.Mol, dict[str, Any]]:
    """Restore known chemistry while preserving every docked heavy-atom coordinate."""

    predicted_path = Path(predicted_path)
    restored_path = Path(restored_path)
    predicted = load_single_unsanitized_pose(predicted_path)
    restored, metadata = restore_docked_pose_chemistry(template, predicted)
    metadata = {
        **metadata,
        "protocol_id": PROTOCOL_ID,
        "predicted_coordinate_source": predicted_path.name,
        "raw_pose_sdf_sha256": sha256_file(predicted_path),
    }
    _write_restored_pose(restored, restored_path)
    metadata["restored_pose_sdf_sha256"] = sha256_file(restored_path)
    return restored, metadata


def _reevaluate_record(record: dict[str, Any], root: Path) -> dict[str, Any]:
    case_id = str(record["result"]["case_id"])
    case_dir = root / case_id
    template = base.load_single_sdf(case_dir / "starting_conformer.sdf")
    reference = base.load_single_sdf(case_dir / "transformed_native_reference.sdf")

    corrected_poses: list[dict[str, Any]] = []
    valid_rmsds: list[float] = []
    first_near_native_rank: int | None = None

    for original in record.get("poses", []):
        rank = int(original["rank"])
        raw_sdf = case_dir / f"pose_{rank:02d}.sdf"
        restored_sdf = case_dir / f"pose_{rank:02d}_chemistry_restored.sdf"
        pose_record: dict[str, Any] = {
            "rank": rank,
            "score_kcal_mol": original.get("score_kcal_mol"),
            "pdbqt_sha256": original.get("pdbqt_sha256"),
        }
        try:
            restored, normalization = restore_pose_for_evaluation(
                template, raw_sdf, restored_sdf
            )
            rmsd = rmsd_evaluator.symmetry_aware_pose_rmsd(reference, restored)
            pose_record.update(rmsd.to_dict())
            pose_record["representation_normalization"] = normalization
            if rmsd.rmsd_angstrom is not None:
                valid_rmsds.append(float(rmsd.rmsd_angstrom))
                if (
                    first_near_native_rank is None
                    and rmsd.rmsd_angstrom <= POSE_SUCCESS_THRESHOLD_ANGSTROM
                ):
                    first_near_native_rank = rank
        except Exception as exc:
            pose_record.update(
                {
                    "status": "INDETERMINATE",
                    "rmsd_angstrom": None,
                    "rmsd_le_2_angstrom": None,
                    "reason": str(exc),
                    "representation_normalization": {
                        "protocol_id": PROTOCOL_ID,
                        "predicted_coordinate_source": raw_sdf.name,
                        "error": str(exc),
                    },
                }
            )
        corrected_poses.append(pose_record)

    if not corrected_poses:
        raise RuntimeError(f"{case_id}: Vina returned no poses to re-evaluate")

    pose1 = corrected_poses[0]
    pose1_rmsd = pose1.get("rmsd_angstrom")
    pose1_score = pose1.get("score_kcal_mol")
    status = "PASS" if pose1_rmsd is not None else "INDETERMINATE"
    pose1_success = bool(
        pose1_rmsd is not None
        and float(pose1_rmsd) <= POSE_SUCCESS_THRESHOLD_ANGSTROM
    )

    corrected = dict(record)
    corrected["poses"] = corrected_poses
    corrected["result"] = {
        "case_id": case_id,
        "status": status,
        "pose_1_rmsd_angstrom": pose1_rmsd,
        "minimum_rmsd_angstrom": min(valid_rmsds) if valid_rmsds else None,
        "pose_count": len(corrected_poses),
        "vina_pose_1_score_kcal_mol": pose1_score,
        "pose_1_success": pose1_success,
        "first_near_native_rank": first_near_native_rank,
        "first_loss": None if status == "PASS" else "POSE_1_RMSD_INDETERMINATE",
    }
    corrected["provenance"] = {
        **dict(record.get("provenance") or {}),
        "pose_representation_protocol_id": PROTOCOL_ID,
    }
    return corrected


def scientific_payload(report: dict[str, Any]) -> dict[str, Any]:
    records = []
    for record in report["records"]:
        provenance = record.get("provenance") or {}
        preparation = provenance.get("preparation") or {}
        docking = provenance.get("docking") or {}
        records.append(
            {
                "case": record.get("case"),
                "result": record.get("result"),
                "structural_identity": provenance.get("structural_identity"),
                "alignment": provenance.get("alignment"),
                "engine_versions": {
                    "vina": (provenance.get("engines") or {}).get("vina", {}).get("version"),
                    "openbabel": (provenance.get("engines") or {}).get("openbabel", {}).get("version"),
                },
                "preparation": {
                    name: {
                        key: (preparation.get(name) or {}).get(key)
                        for key in (
                            "returncode",
                            "engine",
                            "engine_version",
                            "status",
                            "output_sha256",
                            "timed_out",
                            "protocol_id",
                        )
                    }
                    for name in ("receptor", "ligand")
                },
                "docking": {
                    key: docking.get(key)
                    for key in (
                        "best_affinity_kcal_mol",
                        "returncode",
                        "engine",
                        "engine_version",
                        "status",
                        "receptor_sha256",
                        "ligand_sha256",
                        "output_sha256",
                        "grid_hash",
                        "target_id",
                        "protocol_id",
                        "timed_out",
                    )
                },
                "poses": [
                    {
                        "rank": pose.get("rank"),
                        "score_kcal_mol": pose.get("score_kcal_mol"),
                        "status": pose.get("status"),
                        "rmsd_angstrom": pose.get("rmsd_angstrom"),
                        "reference_heavy_atoms": pose.get("reference_heavy_atoms"),
                        "predicted_heavy_atoms": pose.get("predicted_heavy_atoms"),
                        "reference_identity": pose.get("reference_identity"),
                        "predicted_identity": pose.get("predicted_identity"),
                        "rmsd_le_2_angstrom": pose.get("rmsd_le_2_angstrom"),
                        "pdbqt_sha256": pose.get("pdbqt_sha256"),
                        "representation_normalization": {
                            key: (pose.get("representation_normalization") or {}).get(key)
                            for key in (
                                "protocol_id",
                                "method",
                                "template_source",
                                "predicted_coordinate_source",
                                "crystal_coordinates_used_for_mapping",
                                "rigid_fit_performed",
                                "minimization_performed",
                                "heavy_atoms",
                                "atom_mapping_predicted_to_template",
                                "max_heavy_atom_coordinate_delta_angstrom",
                                "template_connectivity_identity",
                                "predicted_connectivity_identity",
                                "template_formula",
                                "restored_formula",
                            )
                        },
                    }
                    for pose in record.get("poses", [])
                ],
            }
        )

    return _normalize(
        {
            "benchmark_id": report["benchmark_id"],
            "docking_protocol_id": report["protocol_id"],
            "pose_representation_protocol_id": report["pose_representation_protocol_id"],
            "rmsd_evaluator_protocol_id": report["evaluator_protocol_id"],
            "preflight_selection_manifest_hash": report["preflight"][
                "selection_manifest_hash"
            ],
            "frozen_cases": report["frozen_cases"],
            "records": records,
            "summary": report["summary"],
        }
    )


def scientific_result_hash(report: dict[str, Any]) -> str:
    return sha256_json(scientific_payload(report))


def run_corrected_crossdock001(workdir: str | Path) -> dict[str, Any]:
    """Run frozen docking, then evaluate all poses with representation-safe v1.1."""

    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    raw_report = run_frozen_crossdock001(root)
    corrected_records = [
        _reevaluate_record(record, root) for record in raw_report["records"]
    ]
    summary = summarize_crossdock(corrected_records)

    report: dict[str, Any] = {
        "benchmark_id": crossdock001.BENCHMARK_ID,
        "protocol_id": crossdock001.PROTOCOL_ID,
        "pose_representation_protocol_id": PROTOCOL_ID,
        "evaluator_protocol_id": rmsd_evaluator.PROTOCOL_ID,
        "preflight": raw_report["preflight"],
        "frozen_cases": raw_report["frozen_cases"],
        "records": corrected_records,
        "summary": summary,
        "audit_history": {
            "invalidated_direct_sdf_run_id": INVALIDATED_V10_RUN_ID,
            "invalidated_direct_sdf_scientific_result_hash": INVALIDATED_V10_SCIENTIFIC_RESULT_HASH,
            "invalidated_direct_sdf_artifact_id": INVALIDATED_V10_ARTIFACT_ID,
            "invalidated_direct_sdf_artifact_zip_sha256": INVALIDATED_V10_ARTIFACT_ZIP_SHA256,
            "invalidation_reason": (
                "direct Open Babel PDBQT-to-SDF chemistry reconstruction left "
                "XDK-05-1 unsanitizable, so only 9/10 frozen pose-1 endpoints "
                "were evaluable despite Vina completing all ten cases"
            ),
        },
        "environment": raw_report["environment"],
    }
    scientific_hash = scientific_result_hash(report)
    report["scientific_result_hash"] = scientific_hash
    report["execution_hash"] = sha256_json(
        {
            "scientific_result_hash": scientific_hash,
            "environment": _normalize(report["environment"]),
        }
    )
    output = root / "crossdock001-result-v1.1.json"
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return report
