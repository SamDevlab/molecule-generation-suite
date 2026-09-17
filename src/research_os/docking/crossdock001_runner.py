from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
import platform
import statistics
import time
from typing import Any

from rdkit import Chem

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking import crossdock001
from research_os.docking import redocking as base
from research_os.docking import redocking_v12 as evaluator
from research_os.docking.crossdock001_freeze import (
    FROZEN_DIRECTED_STRUCTURAL_IDENTITIES,
    PREFLIGHT_ARTIFACT_ID,
    PREFLIGHT_ARTIFACT_ZIP_SHA256,
    PREFLIGHT_RUN_ID,
    PREFLIGHT_SELECTION_MANIFEST_HASH,
)
from research_os.docking.crossdock_alignment import (
    kabsch_source_to_target,
    matched_pocket_ca_pairs,
    parse_ligand_instance,
    parse_protein_chain,
    target_pocket_residue_indices,
)
from research_os.docking.crossdock_identity import stable_hash
from research_os.docking.schema import DockingRequest, GridBox
from research_os.engines.openbabel import OpenBabelEngine
from research_os.engines.vina import VinaEngine


POSE_SUCCESS_THRESHOLD_ANGSTROM = 2.0


def _download_with_retry(url: str, path: Path, *, attempts: int = 4) -> str:
    """Retry transient RCSB transport errors while preserving exact content identity."""

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return base._download(url, path)
        except Exception as exc:
            last_error = exc
            if attempt + 1 == attempts:
                break
            time.sleep(2 ** attempt)
    raise RuntimeError(f"download failed after {attempts} attempts for {url}: {last_error}")


def _reference_heavy_coordinates(mol: Chem.Mol) -> list[tuple[float, float, float]]:
    if mol.GetNumConformers() != 1:
        raise ValueError("reference molecule must contain exactly one conformer")
    conf = mol.GetConformer()
    points: list[tuple[float, float, float]] = []
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() == 1:
            continue
        point = conf.GetAtomPosition(atom.GetIdx())
        points.append((float(point.x), float(point.y), float(point.z)))
    if not points:
        raise ValueError("reference molecule contains no heavy atoms")
    return points


def _coordinate_hash(points: list[tuple[float, float, float]]) -> str:
    return sha256_json([[round(value, 6) for value in point] for point in points])


def _union_grid(points: list[tuple[float, float, float]]) -> dict[str, Any]:
    mins = [min(point[axis] for point in points) for axis in range(3)]
    maxs = [max(point[axis] for point in points) for axis in range(3)]
    center = [(low + high) / 2.0 for low, high in zip(mins, maxs)]
    spans = [high - low for low, high in zip(mins, maxs)]
    required = [span + 2.0 * base.BOX_PADDING_ANGSTROM for span in spans]
    sizes = [
        min(max(side, base.BOX_MIN_SIDE_ANGSTROM), base.BOX_MAX_SIDE_ANGSTROM)
        for side in required
    ]
    status = "PASS"
    reason = None
    if any(side > base.BOX_MAX_SIDE_ANGSTROM for side in required):
        status = "OUT_OF_DOMAIN"
        reason = "target-pocket plus transformed-native reference requires a grid side larger than 30 Å"
    payload: dict[str, Any] = {
        "center": center,
        "size": sizes,
        "unclamped_size": required,
        "status": status,
        "reason": reason,
    }
    payload["grid_hash"] = stable_hash(payload)
    return payload


def _provisional_case(structure: crossdock001.SelectedStructure, target_name: str) -> base.RedockingCase:
    return base.RedockingCase(
        case_id=f"XDK-{structure.pdb_id}",
        pdb_id=structure.pdb_id,
        ligand_id=structure.ligand_id,
        ligand_author_chain=structure.ligand_author_chain,
        receptor_author_chains=(structure.receptor_author_chain,),
        target=target_name,
        resolution_angstrom=0.0,
        source_url=f"https://www.rcsb.org/structure/{structure.pdb_id}",
    )


def _download_pdb(structure: crossdock001.SelectedStructure, root: Path) -> tuple[Path, str, str]:
    path = root / "sources" / f"{structure.pdb_id}.pdb"
    digest = _download_with_retry(f"https://files.rcsb.org/download/{structure.pdb_id}.pdb", path)
    return path, digest, path.read_text(encoding="utf-8", errors="replace")


def _download_reference(
    structure: crossdock001.SelectedStructure,
    auth_seq_id: int,
    target_name: str,
    root: Path,
) -> tuple[Path, Chem.Mol]:
    case = _provisional_case(structure, target_name)
    path = root / "sources" / f"{structure.pdb_id}-{structure.ligand_id}-reference.sdf"
    _download_with_retry(base._instance_sdf_url(case, auth_seq_id), path)
    return path, base.load_single_sdf(path)


def _target_receptor_pdb(pdb_text: str, chain: str) -> str:
    lines = [
        line
        for line in pdb_text.splitlines()
        if len(line) >= 22
        and line[:6].strip() == "ATOM"
        and line[21].strip() == chain
        and base._primary_altloc(line)
    ]
    if not lines:
        raise ValueError(f"target receptor chain {chain!r} contains no ATOM records")
    return "\n".join(lines + ["TER", "END"]) + "\n"


def _transform_reference(mol: Chem.Mol, transform: Any, output_path: Path) -> Chem.Mol:
    transformed = Chem.Mol(mol)
    if transformed.GetNumConformers() != 1:
        raise ValueError("source reference must contain exactly one conformer")
    conf = transformed.GetConformer()
    all_points = []
    for atom_index in range(transformed.GetNumAtoms()):
        point = conf.GetAtomPosition(atom_index)
        all_points.append((float(point.x), float(point.y), float(point.z)))
    moved = transform.apply(all_points)
    for atom_index, (x, y, z) in enumerate(moved):
        conf.SetAtomPosition(atom_index, (x, y, z))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = Chem.SDWriter(str(output_path))
    writer.write(transformed)
    writer.close()
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("transformed source reference SDF was not written")
    return transformed


def _prepare_structural_case(case: dict[str, object], case_dir: Path) -> dict[str, Any]:
    case_id = str(case["case_id"])
    source = crossdock001.SelectedStructure(**dict(case["source"]))
    target = crossdock001.SelectedStructure(**dict(case["target"]))
    target_name = str(case["target_name"])
    expected = FROZEN_DIRECTED_STRUCTURAL_IDENTITIES[case_id]

    source_path, source_pdb_sha256, source_text = _download_pdb(source, case_dir)
    target_path, target_pdb_sha256, target_text = _download_pdb(target, case_dir)
    if source_pdb_sha256 != expected["source_pdb_sha256"]:
        raise RuntimeError(f"{case_id}: source PDB identity changed")
    if target_pdb_sha256 != expected["target_pdb_sha256"]:
        raise RuntimeError(f"{case_id}: target PDB identity changed")

    source_residues = parse_protein_chain(source_text, source.receptor_author_chain)
    target_residues = parse_protein_chain(target_text, target.receptor_author_chain)
    source_ligand = parse_ligand_instance(
        source_text,
        ligand_id=source.ligand_id,
        ligand_author_chain=source.ligand_author_chain,
    )
    target_ligand = parse_ligand_instance(
        target_text,
        ligand_id=target.ligand_id,
        ligand_author_chain=target.ligand_author_chain,
    )
    pocket = target_pocket_residue_indices(
        target_residues,
        target_ligand,
        cutoff_angstrom=crossdock001.POCKET_CUTOFF_ANGSTROM,
    )
    pairs = matched_pocket_ca_pairs(source_residues, target_residues, pocket)
    if len(pairs) != int(expected["matched_identical_pocket_ca_pairs"]):
        raise RuntimeError(f"{case_id}: frozen receptor-pocket correspondence changed")
    transform = kabsch_source_to_target(pairs)

    source_reference_path, source_reference = _download_reference(
        source, source_ligand.auth_seq_id, target_name, case_dir
    )
    _, target_reference = _download_reference(
        target, target_ligand.auth_seq_id, target_name, case_dir
    )
    source_xyz = _reference_heavy_coordinates(source_reference)
    target_xyz = _reference_heavy_coordinates(target_reference)
    if len(source_xyz) != len(source_ligand.heavy_xyz):
        raise RuntimeError(f"{case_id}: source reference/PDB heavy-atom count mismatch")
    if len(target_xyz) != len(target_ligand.heavy_xyz):
        raise RuntimeError(f"{case_id}: target reference/PDB heavy-atom count mismatch")
    if _coordinate_hash(target_xyz) != expected["target_reference_coordinate_hash"]:
        raise RuntimeError(f"{case_id}: target reference coordinates changed")

    transformed_xyz = transform.apply(source_xyz)
    if _coordinate_hash(transformed_xyz) != expected["transformed_source_reference_coordinate_hash"]:
        raise RuntimeError(f"{case_id}: transformed source reference identity changed")
    grid = _union_grid(transformed_xyz + list(target_ligand.heavy_xyz))
    if grid["status"] != "PASS" or grid["grid_hash"] != expected["grid_hash"]:
        raise RuntimeError(f"{case_id}: frozen cross-docking grid identity changed")

    receptor_pdb = case_dir / "target_receptor.pdb"
    receptor_pdb.write_text(
        _target_receptor_pdb(target_text, target.receptor_author_chain), encoding="utf-8"
    )
    transformed_reference_sdf = case_dir / "transformed_native_reference.sdf"
    transformed_reference = _transform_reference(source_reference, transform, transformed_reference_sdf)
    if _coordinate_hash(_reference_heavy_coordinates(transformed_reference)) != expected[
        "transformed_source_reference_coordinate_hash"
    ]:
        raise RuntimeError(f"{case_id}: written transformed reference coordinates changed")

    return {
        "case_id": case_id,
        "case": case,
        "source": source,
        "target": target,
        "source_pdb_path": source_path,
        "target_pdb_path": target_path,
        "source_reference_path": source_reference_path,
        "source_reference": source_reference,
        "transformed_reference": transformed_reference,
        "transformed_reference_sdf": transformed_reference_sdf,
        "receptor_pdb": receptor_pdb,
        "grid": grid,
        "alignment": {
            "matched_identical_pocket_ca_pairs": len(pairs),
            "rmsd_angstrom": transform.rmsd_angstrom,
            "rotation": transform.rotation,
            "translation": transform.translation,
        },
        "structural_identity": dict(expected),
    }


def _case_failure(case: dict[str, object], first_loss: str, detail: str) -> dict[str, Any]:
    return {
        "case": case,
        "result": {
            "case_id": str(case["case_id"]),
            "status": "INDETERMINATE",
            "pose_1_rmsd_angstrom": None,
            "minimum_rmsd_angstrom": None,
            "pose_count": 0,
            "vina_pose_1_score_kcal_mol": None,
            "pose_1_success": False,
            "first_near_native_rank": None,
            "first_loss": first_loss,
        },
        "poses": [],
        "provenance": {"error": detail},
    }


def run_crossdock_case(
    case: dict[str, object],
    workdir: str | Path,
    *,
    vina: VinaEngine | None = None,
    obabel: OpenBabelEngine | None = None,
) -> dict[str, Any]:
    case_id = str(case["case_id"])
    case_dir = Path(workdir) / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    try:
        prepared = _prepare_structural_case(case, case_dir)
    except Exception as exc:
        return _case_failure(case, "STRUCTURAL_FREEZE_MISMATCH", str(exc))

    vina_engine = vina or VinaEngine()
    openbabel = obabel or OpenBabelEngine()
    provenance: dict[str, Any] = {
        "protocol_id": crossdock001.PROTOCOL_ID,
        "preflight_selection_manifest_hash": PREFLIGHT_SELECTION_MANIFEST_HASH,
        "structural_identity": prepared["structural_identity"],
        "alignment": prepared["alignment"],
        "engines": {
            "vina": {"version": vina_engine.version, "path": vina_engine.executable},
            "openbabel": {"version": openbabel.version, "path": openbabel.executable},
        },
    }
    if not openbabel.available:
        return _case_failure(case, "OPENBABEL_UNAVAILABLE", "Open Babel executable is unavailable")
    if not vina_engine.available:
        return _case_failure(case, "VINA_UNAVAILABLE", "AutoDock Vina executable is unavailable")
    if not vina_engine.version or "1.2.7" not in vina_engine.version:
        return _case_failure(case, "VINA_VERSION_MISMATCH", repr(vina_engine.version))

    starting_sdf = case_dir / "starting_conformer.sdf"
    try:
        provenance["starting_conformer"] = base.generate_independent_conformer(
            prepared["source_reference"], starting_sdf
        )
    except Exception as exc:
        return _case_failure(case, "CONFORMER_GENERATION_FAILED", str(exc))

    receptor_pdbqt = case_dir / "receptor.pdbqt"
    ligand_pdbqt = case_dir / "ligand.pdbqt"
    try:
        receptor_prep = openbabel.convert(
            prepared["receptor_pdb"],
            receptor_pdbqt,
            options=("-h", "--partialcharge", "gasteiger", "-xr"),
            timeout=120.0,
            protocol_id="crossdock001.v1.0.receptor-openbabel",
        )
        ligand_prep = openbabel.convert(
            starting_sdf,
            ligand_pdbqt,
            options=("-h", "--partialcharge", "gasteiger"),
            timeout=120.0,
            protocol_id="crossdock001.v1.0.ligand-openbabel",
        )
    except Exception as exc:
        return _case_failure(case, "PDBQT_PREPARATION_FAILED", str(exc))
    provenance["preparation"] = {
        "receptor": asdict(receptor_prep),
        "ligand": asdict(ligand_prep),
    }
    if receptor_prep.returncode != 0 or not receptor_prep.output_sha256:
        return _case_failure(case, "RECEPTOR_PREPARATION_FAILED", receptor_prep.stderr)
    if ligand_prep.returncode != 0 or not ligand_prep.output_sha256:
        return _case_failure(case, "LIGAND_PREPARATION_FAILED", ligand_prep.stderr)

    grid = prepared["grid"]
    vina_output = case_dir / "vina_poses.pdbqt"
    request = DockingRequest(
        receptor_path=str(receptor_pdbqt),
        ligand_path=str(ligand_pdbqt),
        grid=GridBox(
            float(grid["center"][0]),
            float(grid["center"][1]),
            float(grid["center"][2]),
            float(grid["size"][0]),
            float(grid["size"][1]),
            float(grid["size"][2]),
        ),
        exhaustiveness=base.VINA_EXHAUSTIVENESS,
        cpu=base.VINA_CPU,
        seed=base.VINA_SEED,
        output_path=str(vina_output),
        target_id=f"{case['source']['pdb_id']}->{case['target']['pdb_id']}",
        protocol_id=crossdock001.PROTOCOL_ID,
        timeout=900.0,
        num_modes=base.VINA_NUM_MODES,
    )
    try:
        docking = vina_engine.run(request)
    except Exception as exc:
        return _case_failure(case, "DOCKING_FAILED", str(exc))
    provenance["docking"] = docking.to_dict()
    if docking.returncode != 0 or not vina_output.is_file():
        return _case_failure(case, "DOCKING_FAILED", docking.stderr)

    pdbqt_text = vina_output.read_text(encoding="utf-8", errors="replace")
    model_blocks = base.split_vina_pdbqt_models(pdbqt_text)
    scores = base.parse_vina_pose_scores(pdbqt_text)
    if not model_blocks:
        return _case_failure(case, "NO_DOCKED_POSES", "Vina produced no parseable models")

    poses: list[dict[str, Any]] = []
    valid_rmsds: list[float] = []
    first_near_native_rank: int | None = None
    reference = prepared["transformed_reference"]
    for rank, block in enumerate(model_blocks, start=1):
        pose_pdbqt = case_dir / f"pose_{rank:02d}.pdbqt"
        pose_sdf = case_dir / f"pose_{rank:02d}.sdf"
        pose_pdbqt.write_text(block, encoding="utf-8")
        pose_record: dict[str, Any] = {
            "rank": rank,
            "score_kcal_mol": scores[rank - 1] if rank <= len(scores) else None,
            "pdbqt_sha256": sha256_file(pose_pdbqt),
        }
        try:
            conversion = openbabel.convert(
                pose_pdbqt,
                pose_sdf,
                timeout=60.0,
                protocol_id="crossdock001.v1.0.pose-openbabel",
            )
            if conversion.returncode != 0 or not pose_sdf.is_file():
                raise RuntimeError("pose conversion failed")
            pose_molecules = base.load_pose_sdf(pose_sdf)
            if len(pose_molecules) != 1:
                raise RuntimeError(f"expected one converted pose, found {len(pose_molecules)}")
            rmsd = evaluator.symmetry_aware_pose_rmsd(reference, pose_molecules[0])
            pose_record.update(rmsd.to_dict())
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
                }
            )
        poses.append(pose_record)

    pose1 = poses[0]
    pose1_rmsd = pose1.get("rmsd_angstrom")
    pose1_score = pose1.get("score_kcal_mol")
    status = "PASS" if pose1_rmsd is not None else "INDETERMINATE"
    pose1_success = bool(
        pose1_rmsd is not None and float(pose1_rmsd) <= POSE_SUCCESS_THRESHOLD_ANGSTROM
    )
    return {
        "case": case,
        "result": {
            "case_id": case_id,
            "status": status,
            "pose_1_rmsd_angstrom": pose1_rmsd,
            "minimum_rmsd_angstrom": min(valid_rmsds) if valid_rmsds else None,
            "pose_count": len(poses),
            "vina_pose_1_score_kcal_mol": pose1_score,
            "pose_1_success": pose1_success,
            "first_near_native_rank": first_near_native_rank,
            "first_loss": None if status == "PASS" else "POSE_1_RMSD_INDETERMINATE",
        },
        "poses": poses,
        "provenance": provenance,
    }


def summarize_crossdock(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    evaluable = [record for record in records if record["result"]["pose_1_rmsd_angstrom"] is not None]
    successes = [record for record in records if record["result"]["pose_1_success"]]
    pose1_values = [float(record["result"]["pose_1_rmsd_angstrom"]) for record in evaluable]
    any_near_native = [
        record for record in records if record["result"].get("first_near_native_rank") is not None
    ]
    return {
        "total_cases": total,
        "evaluable_pose_1_cases": len(evaluable),
        "pose_1_rmsd_le_2_angstrom": {
            "count": len(successes),
            "denominator": total,
            "fraction": len(successes) / total if total else 0.0,
        },
        "any_returned_pose_rmsd_le_2_angstrom": {
            "count": len(any_near_native),
            "denominator": total,
            "fraction": len(any_near_native) / total if total else 0.0,
        },
        "pose_1_rmsd_mean_angstrom": statistics.fmean(pose1_values) if pose1_values else None,
        "pose_1_rmsd_median_angstrom": statistics.median(pose1_values) if pose1_values else None,
    }


def _normalize(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 12)
    if isinstance(value, dict):
        return {key: _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


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
                        key: pose.get(key)
                        for key in (
                            "rank",
                            "score_kcal_mol",
                            "status",
                            "rmsd_angstrom",
                            "reference_heavy_atoms",
                            "predicted_heavy_atoms",
                            "reference_identity",
                            "predicted_identity",
                            "rmsd_le_2_angstrom",
                            "pdbqt_sha256",
                        )
                    }
                    for pose in record.get("poses", [])
                ],
            }
        )
    return _normalize(
        {
            "benchmark_id": report["benchmark_id"],
            "protocol_id": report["protocol_id"],
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


def run_frozen_crossdock001(workdir: str | Path) -> dict[str, Any]:
    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    vina = VinaEngine()
    obabel = OpenBabelEngine()
    cases = list(crossdock001.directed_case_specs())
    if len(cases) != crossdock001.DIRECTED_CASE_COUNT:
        raise RuntimeError("frozen directed case count changed")
    records = [run_crossdock_case(case, root, vina=vina, obabel=obabel) for case in cases]
    summary = summarize_crossdock(records)
    report: dict[str, Any] = {
        "benchmark_id": crossdock001.BENCHMARK_ID,
        "protocol_id": crossdock001.PROTOCOL_ID,
        "evaluator_protocol_id": evaluator.PROTOCOL_ID,
        "preflight": {
            "run_id": PREFLIGHT_RUN_ID,
            "artifact_id": PREFLIGHT_ARTIFACT_ID,
            "artifact_zip_sha256": PREFLIGHT_ARTIFACT_ZIP_SHA256,
            "selection_manifest_hash": PREFLIGHT_SELECTION_MANIFEST_HASH,
            "docking_executed_in_preflight": False,
        },
        "frozen_cases": cases,
        "records": records,
        "summary": summary,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "vina_version": vina.version,
            "openbabel_version": obabel.version,
        },
    }
    scientific_hash = scientific_result_hash(report)
    report["scientific_result_hash"] = scientific_hash
    report["execution_hash"] = sha256_json(
        {
            "scientific_result_hash": scientific_hash,
            "environment": _normalize(report["environment"]),
        }
    )
    output = root / "crossdock001-result-v1.0.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return report
