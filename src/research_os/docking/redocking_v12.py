from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
import platform
import statistics
from typing import Sequence

from rdkit import Chem

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking import redocking as v11
from research_os.docking.schema import DockingRequest, GridBox
from research_os.engines.openbabel import OpenBabelEngine
from research_os.engines.vina import VinaEngine


PROTOCOL_ID = "research-os.redocking.v1.2"
POSE_SUCCESS_THRESHOLD_ANGSTROM = 2.0
SYMMETRY_MAX_MATCHES = 10000


# The frozen cases and all docking/search parameters are intentionally inherited
# unchanged from v1.1. Only the pose-localization evaluator is corrected.
FROZEN_REDOCKING_CASES = v11.FROZEN_REDOCKING_CASES


def _same_frame_rmsd_for_mapping(reference: Chem.Mol, predicted: Chem.Mol, match: tuple[int, ...]) -> float:
    """Cartesian RMSD for one graph mapping without fitting either molecule."""

    ref_conf = reference.GetConformer()
    pred_conf = predicted.GetConformer()
    squared = 0.0
    for pred_idx, ref_idx in enumerate(match):
        pred_pos = pred_conf.GetAtomPosition(pred_idx)
        ref_pos = ref_conf.GetAtomPosition(ref_idx)
        dx = pred_pos.x - ref_pos.x
        dy = pred_pos.y - ref_pos.y
        dz = pred_pos.z - ref_pos.z
        squared += dx * dx + dy * dy + dz * dz
    return math.sqrt(squared / predicted.GetNumAtoms())


def symmetry_aware_pose_rmsd(reference: Chem.Mol, predicted: Chem.Mol) -> v11.PoseRmsdResult:
    """Symmetry-aware heavy-atom pose RMSD in the receptor coordinate frame.

    The predicted ligand is never translated, rotated, fitted, or superposed onto
    the crystallographic reference. Only graph-isomorphic atom correspondence is
    optimized. This is the v1.2 correction over the aligned v1.1 evaluator.
    """

    try:
        ref = v11._connectivity_graph(reference)
        pred = v11._connectivity_graph(predicted)
        ref_identity = Chem.MolToSmiles(ref, canonical=True, isomericSmiles=False)
        pred_identity = Chem.MolToSmiles(pred, canonical=True, isomericSmiles=False)
    except ValueError as exc:
        return v11.PoseRmsdResult("INDETERMINATE", None, 0, 0, None, None, reason=str(exc))

    if ref.GetNumAtoms() != pred.GetNumAtoms():
        return v11.PoseRmsdResult(
            "INDETERMINATE",
            None,
            ref.GetNumAtoms(),
            pred.GetNumAtoms(),
            ref_identity,
            pred_identity,
            reason="heavy-atom counts differ",
        )
    if ref.GetNumBonds() != pred.GetNumBonds() or ref_identity != pred_identity:
        return v11.PoseRmsdResult(
            "INDETERMINATE",
            None,
            ref.GetNumAtoms(),
            pred.GetNumAtoms(),
            ref_identity,
            pred_identity,
            reason="reference and predicted heavy-atom graphs differ",
        )

    matches = ref.GetSubstructMatches(
        pred,
        uniquify=False,
        useChirality=False,
        maxMatches=SYMMETRY_MAX_MATCHES,
    )
    if not matches:
        return v11.PoseRmsdResult(
            "INDETERMINATE",
            None,
            ref.GetNumAtoms(),
            pred.GetNumAtoms(),
            ref_identity,
            pred_identity,
            reason="no exact symmetry-aware graph mapping was found",
        )
    if len(matches) >= SYMMETRY_MAX_MATCHES:
        return v11.PoseRmsdResult(
            "INDETERMINATE",
            None,
            ref.GetNumAtoms(),
            pred.GetNumAtoms(),
            ref_identity,
            pred_identity,
            reason="symmetry mapping enumeration limit was reached",
        )

    best = min(_same_frame_rmsd_for_mapping(ref, pred, tuple(match)) for match in matches)
    if not math.isfinite(best):
        return v11.PoseRmsdResult(
            "INDETERMINATE",
            None,
            ref.GetNumAtoms(),
            pred.GetNumAtoms(),
            ref_identity,
            pred_identity,
            reason="RMSD is non-finite",
        )
    return v11.PoseRmsdResult(
        "PASS",
        float(best),
        ref.GetNumAtoms(),
        pred.GetNumAtoms(),
        ref_identity,
        pred_identity,
    )


def derive_redocking_grid(reference: Chem.Mol) -> v11.RedockingGrid:
    heavy = v11._heavy_atom_copy(reference)
    conf = heavy.GetConformer()
    coords = [conf.GetAtomPosition(index) for index in range(heavy.GetNumAtoms())]
    mins = [min(getattr(point, axis) for point in coords) for axis in ("x", "y", "z")]
    maxs = [max(getattr(point, axis) for point in coords) for axis in ("x", "y", "z")]
    center = [(low + high) / 2.0 for low, high in zip(mins, maxs)]
    spans = [high - low for low, high in zip(mins, maxs)]
    required = [span + 2.0 * v11.BOX_PADDING_ANGSTROM for span in spans]
    sizes = [
        min(max(side, v11.BOX_MIN_SIDE_ANGSTROM), v11.BOX_MAX_SIDE_ANGSTROM)
        for side in required
    ]
    status = "PASS"
    reason = None
    if any(side > v11.BOX_MAX_SIDE_ANGSTROM for side in required):
        status = "OUT_OF_DOMAIN"
        reason = "native-ligand box rule requires a side larger than 30 Å"
    grid_hash = sha256_json(
        {
            "protocol_id": PROTOCOL_ID,
            "center": center,
            "size": sizes,
            "unclamped_size": required,
            "status": status,
            "reason": reason,
        }
    )
    return v11.RedockingGrid(
        *center,
        *sizes,
        *required,
        status=status,
        reason=reason,
        grid_hash=grid_hash,
    )


def evaluate_pose_files(reference_sdf: str | Path, predicted_sdf: str | Path) -> list[v11.PoseRmsdResult]:
    reference = v11.load_single_sdf(reference_sdf)
    reference_hash = sha256_file(reference_sdf)
    predicted_hash = sha256_file(predicted_sdf)
    results: list[v11.PoseRmsdResult] = []
    for pose in v11.load_pose_sdf(predicted_sdf):
        raw = symmetry_aware_pose_rmsd(reference, pose)
        results.append(
            v11.PoseRmsdResult(
                raw.status,
                raw.rmsd_angstrom,
                raw.reference_heavy_atoms,
                raw.predicted_heavy_atoms,
                raw.reference_identity,
                raw.predicted_identity,
                reference_sha256=reference_hash,
                predicted_sha256=predicted_hash,
                reason=raw.reason,
            )
        )
    return results


def _case_failure(
    case: v11.RedockingCase,
    status: str,
    first_loss: str,
    provenance: dict[str, object],
    *,
    pose_count: int = 0,
) -> dict[str, object]:
    result = v11.RedockingCaseResult(case.case_id, status, None, None, pose_count, first_loss=first_loss)
    return {"case": case.to_dict(), "result": result.to_dict(), "provenance": provenance, "poses": []}


def run_redocking_case(
    case: v11.RedockingCase,
    workdir: str | Path,
    *,
    vina: VinaEngine | None = None,
    obabel: OpenBabelEngine | None = None,
) -> dict[str, object]:
    """Execute one frozen v1.2 case with unchanged docking parameters."""

    case_dir = Path(workdir) / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    provenance: dict[str, object] = {"protocol_id": PROTOCOL_ID}

    raw_url = f"https://files.rcsb.org/download/{case.pdb_id}.pdb"
    raw_path = case_dir / f"{case.pdb_id}.pdb"
    try:
        provenance["raw_pdb"] = {"url": raw_url, "sha256": v11._download(raw_url, raw_path)}
        pdb_text = raw_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        provenance["error"] = str(exc)
        return _case_failure(case, "INDETERMINATE", "RCSB_DOWNLOAD_FAILED", provenance)

    try:
        extraction = v11.extract_case_from_pdb(pdb_text, case)
    except Exception as exc:
        provenance["error"] = str(exc)
        return _case_failure(case, "INDETERMINATE", "PDB_EXTRACTION_FAILED", provenance)

    receptor_pdb = case_dir / "receptor_extracted.pdb"
    ligand_pdb = case_dir / "native_ligand_extracted.pdb"
    receptor_pdb.write_text(extraction.receptor_pdb, encoding="utf-8")
    ligand_pdb.write_text(extraction.ligand_pdb, encoding="utf-8")
    provenance["extraction"] = {
        "ligand_auth_seq_id": extraction.ligand_auth_seq_id,
        "ligand_insertion_code": extraction.ligand_insertion_code,
        "ligand_heavy_atoms_from_pdb": extraction.ligand_heavy_atoms,
        "receptor_atom_count": extraction.receptor_atom_count,
        "receptor_sha256": sha256_file(receptor_pdb),
        "native_ligand_pdb_sha256": sha256_file(ligand_pdb),
    }

    reference_url = v11._instance_sdf_url(case, extraction.ligand_auth_seq_id)
    reference_sdf = case_dir / "native_reference.sdf"
    try:
        reference_hash = v11._download(reference_url, reference_sdf)
        reference = v11.load_single_sdf(reference_sdf)
    except Exception as exc:
        provenance["reference"] = {"url": reference_url, "error": str(exc)}
        return _case_failure(case, "INDETERMINATE", "REFERENCE_FETCH_OR_PARSE_FAILED", provenance)
    provenance["reference"] = {
        "url": reference_url,
        "sha256": reference_hash,
        "heavy_atoms": reference.GetNumHeavyAtoms(),
    }
    if reference.GetNumHeavyAtoms() != extraction.ligand_heavy_atoms:
        provenance["reference"]["pdb_heavy_atoms"] = extraction.ligand_heavy_atoms
        return _case_failure(case, "INDETERMINATE", "REFERENCE_INSTANCE_MISMATCH", provenance)

    try:
        grid = derive_redocking_grid(reference)
    except Exception as exc:
        provenance["error"] = str(exc)
        return _case_failure(case, "INDETERMINATE", "GRID_DERIVATION_FAILED", provenance)
    provenance["grid"] = grid.to_dict()
    if grid.status != "PASS":
        return _case_failure(case, "OUT_OF_DOMAIN", "BOX_OUT_OF_DOMAIN", provenance)

    starting_sdf = case_dir / "starting_conformer.sdf"
    try:
        provenance["starting_conformer"] = v11.generate_independent_conformer(reference, starting_sdf)
    except Exception as exc:
        provenance["error"] = str(exc)
        return _case_failure(case, "INDETERMINATE", "CONFORMER_GENERATION_FAILED", provenance)

    openbabel = obabel or OpenBabelEngine()
    vina_engine = vina or VinaEngine()
    provenance["engines"] = {
        "openbabel": {"path": openbabel.executable, "version": openbabel.version},
        "vina": {"path": vina_engine.executable, "version": vina_engine.version},
    }
    if not openbabel.available:
        return _case_failure(case, "INDETERMINATE", "OPENBABEL_UNAVAILABLE", provenance)
    if not vina_engine.available:
        return _case_failure(case, "INDETERMINATE", "VINA_UNAVAILABLE", provenance)
    if not vina_engine.version or "1.2.7" not in vina_engine.version:
        return _case_failure(case, "INDETERMINATE", "VINA_VERSION_MISMATCH", provenance)

    receptor_pdbqt = case_dir / "receptor.pdbqt"
    ligand_pdbqt = case_dir / "ligand.pdbqt"
    try:
        receptor_prep = openbabel.convert(
            receptor_pdb,
            receptor_pdbqt,
            options=("-h", "--partialcharge", "gasteiger", "-xr"),
            timeout=120.0,
            protocol_id="redocking.v1.2.receptor-openbabel",
        )
        ligand_prep = openbabel.convert(
            starting_sdf,
            ligand_pdbqt,
            options=("-h", "--partialcharge", "gasteiger"),
            timeout=120.0,
            protocol_id="redocking.v1.2.ligand-openbabel",
        )
    except Exception as exc:
        provenance["error"] = str(exc)
        return _case_failure(case, "INDETERMINATE", "PDBQT_PREPARATION_FAILED", provenance)
    provenance["preparation"] = {"receptor": asdict(receptor_prep), "ligand": asdict(ligand_prep)}
    if receptor_prep.returncode != 0 or not receptor_prep.output_sha256:
        return _case_failure(case, "INDETERMINATE", "RECEPTOR_PREPARATION_FAILED", provenance)
    if ligand_prep.returncode != 0 or not ligand_prep.output_sha256:
        return _case_failure(case, "INDETERMINATE", "LIGAND_PREPARATION_FAILED", provenance)

    vina_output = case_dir / "vina_poses.pdbqt"
    request = DockingRequest(
        receptor_path=str(receptor_pdbqt),
        ligand_path=str(ligand_pdbqt),
        grid=GridBox(grid.center_x, grid.center_y, grid.center_z, grid.size_x, grid.size_y, grid.size_z),
        exhaustiveness=v11.VINA_EXHAUSTIVENESS,
        cpu=v11.VINA_CPU,
        seed=v11.VINA_SEED,
        output_path=str(vina_output),
        target_id=case.pdb_id,
        protocol_id=PROTOCOL_ID,
        timeout=900.0,
        num_modes=v11.VINA_NUM_MODES,
    )
    try:
        docking = vina_engine.run(request)
    except Exception as exc:
        provenance["error"] = str(exc)
        return _case_failure(case, "FAIL", "DOCKING_FAILED", provenance)
    provenance["docking"] = docking.to_dict()
    if docking.returncode != 0 or not vina_output.is_file():
        return _case_failure(case, "FAIL", "DOCKING_FAILED", provenance)

    pdbqt_text = vina_output.read_text(encoding="utf-8", errors="replace")
    model_blocks = v11.split_vina_pdbqt_models(pdbqt_text)
    scores = v11.parse_vina_pose_scores(pdbqt_text)
    if not model_blocks:
        return _case_failure(case, "FAIL", "NO_DOCKED_POSES", provenance)

    pose_results: list[dict[str, object]] = []
    valid_rmsd: list[float] = []
    for index, block in enumerate(model_blocks, start=1):
        pose_pdbqt = case_dir / f"pose_{index:02d}.pdbqt"
        pose_sdf = case_dir / f"pose_{index:02d}.sdf"
        pose_pdbqt.write_text(block, encoding="utf-8")
        try:
            conversion = openbabel.convert(
                pose_pdbqt,
                pose_sdf,
                timeout=60.0,
                protocol_id="redocking.v1.2.pose-openbabel",
            )
            if conversion.returncode != 0 or not pose_sdf.is_file():
                raise RuntimeError("Open Babel pose conversion failed")
            rmsd_result = evaluate_pose_files(reference_sdf, pose_sdf)[0]
        except Exception as exc:
            pose_results.append(
                {
                    "rank": index,
                    "score_kcal_mol": scores[index - 1] if index <= len(scores) else None,
                    "status": "INDETERMINATE",
                    "rmsd_angstrom": None,
                    "reason": str(exc),
                    "pdbqt_sha256": sha256_file(pose_pdbqt),
                    "sdf_sha256": sha256_file(pose_sdf) if pose_sdf.is_file() else None,
                }
            )
            continue
        pose_results.append(
            {
                "rank": index,
                "score_kcal_mol": scores[index - 1] if index <= len(scores) else None,
                **rmsd_result.to_dict(),
                "pdbqt_sha256": sha256_file(pose_pdbqt),
                "sdf_sha256": sha256_file(pose_sdf),
            }
        )
        if rmsd_result.rmsd_angstrom is not None:
            valid_rmsd.append(float(rmsd_result.rmsd_angstrom))

    pose_1 = pose_results[0]
    pose_1_rmsd = pose_1.get("rmsd_angstrom")
    if not isinstance(pose_1_rmsd, (int, float)) or not math.isfinite(float(pose_1_rmsd)):
        result = v11.RedockingCaseResult(
            case.case_id,
            "INDETERMINATE",
            None,
            min(valid_rmsd) if valid_rmsd else None,
            len(model_blocks),
            scores[0] if scores else None,
            "POSE_1_RMSD_INDETERMINATE",
        )
        return {"case": case.to_dict(), "result": result.to_dict(), "provenance": provenance, "poses": pose_results}

    result = v11.RedockingCaseResult(
        case.case_id,
        "PASS",
        float(pose_1_rmsd),
        min(valid_rmsd) if valid_rmsd else float(pose_1_rmsd),
        len(model_blocks),
        scores[0] if scores else None,
    )
    return {"case": case.to_dict(), "result": result.to_dict(), "provenance": provenance, "poses": pose_results}


def summarize_redocking_results(results: Sequence[v11.RedockingCaseResult]) -> dict[str, object]:
    if not results:
        raise ValueError("at least one redocking case result is required")
    case_ids = [item.case_id for item in results]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("redocking case ids must be unique")

    passing = [item for item in results if item.status == "PASS" and item.pose_1_rmsd_angstrom is not None]
    pose_1_values = [float(item.pose_1_rmsd_angstrom) for item in passing]
    successes = sum(
        bool(
            item.status == "PASS"
            and item.pose_1_rmsd_angstrom is not None
            and item.pose_1_rmsd_angstrom <= POSE_SUCCESS_THRESHOLD_ANGSTROM
        )
        for item in results
    )
    statuses: dict[str, int] = {}
    for item in results:
        statuses[item.status] = statuses.get(item.status, 0) + 1

    return {
        "protocol_id": PROTOCOL_ID,
        "total_cases": len(results),
        "passing_rmsd_cases": len(passing),
        "status_counts": dict(sorted(statuses.items())),
        "pose_1_rmsd_angstrom": {
            "mean_over_passing_cases": statistics.fmean(pose_1_values) if pose_1_values else None,
            "median_over_passing_cases": statistics.median(pose_1_values) if pose_1_values else None,
            "values": [item.pose_1_rmsd_angstrom for item in results],
        },
        "pose_1_rmsd_le_2_angstrom": {
            "count": successes,
            "fraction_all_frozen_cases": successes / len(results),
            "denominator": len(results),
        },
        "cases": [item.to_dict() for item in results],
        "interpretation": (
            "same-frame pose reproduction for the frozen benchmark only; docking scores and RMSD do not establish "
            "binding affinity, biological activity, safety, efficacy, or clinical performance"
        ),
        "summary_hash": sha256_json([item.to_dict() for item in results]),
    }


def run_frozen_redocking_benchmark(workdir: str | Path) -> dict[str, object]:
    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    vina = VinaEngine()
    obabel = OpenBabelEngine()
    records = [run_redocking_case(case, root, vina=vina, obabel=obabel) for case in FROZEN_REDOCKING_CASES]
    result_objects = [
        v11.RedockingCaseResult(
            case_id=str(record["result"]["case_id"]),
            status=str(record["result"]["status"]),
            pose_1_rmsd_angstrom=record["result"].get("pose_1_rmsd_angstrom"),
            minimum_rmsd_angstrom=record["result"].get("minimum_rmsd_angstrom"),
            pose_count=int(record["result"].get("pose_count", 0)),
            vina_pose_1_score_kcal_mol=record["result"].get("vina_pose_1_score_kcal_mol"),
            first_loss=record["result"].get("first_loss"),
        )
        for record in records
    ]
    summary = summarize_redocking_results(result_objects)
    scientific_payload = {
        "protocol_id": PROTOCOL_ID,
        "symmetry_mapping_max_matches": SYMMETRY_MAX_MATCHES,
        "frozen_cases": [case.to_dict() for case in FROZEN_REDOCKING_CASES],
        "records": records,
        "summary": summary,
    }
    scientific_result_hash = sha256_json(scientific_payload)
    environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "vina_version": vina.version,
        "openbabel_version": obabel.version,
        "vina_executable": vina.executable,
        "openbabel_executable": obabel.executable,
    }
    execution_hash = sha256_json({"scientific_result_hash": scientific_result_hash, "environment": environment})
    report = {
        **scientific_payload,
        "scientific_result_hash": scientific_result_hash,
        "execution_hash": execution_hash,
        "environment": environment,
    }
    output = root / "redocking-result-v1.2.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return report
