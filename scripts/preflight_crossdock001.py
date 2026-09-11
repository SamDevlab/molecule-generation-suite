from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from rdkit import Chem

from research_os.core.hashing import sha256_json
from research_os.docking import crossdock001
from research_os.docking import redocking as base
from research_os.docking.crossdock_alignment import (
    kabsch_source_to_target,
    matched_pocket_ca_pairs,
    minimum_distance,
    parse_ligand_instance,
    parse_protein_chain,
    target_pocket_residue_indices,
)


def _provisional_case(structure: crossdock001.SelectedStructure, target: str) -> base.RedockingCase:
    return base.RedockingCase(
        case_id=f"PREFLIGHT-{structure.pdb_id}",
        pdb_id=structure.pdb_id,
        ligand_id=structure.ligand_id,
        ligand_author_chain=structure.ligand_author_chain,
        receptor_author_chains=(structure.receptor_author_chain,),
        target=target,
        resolution_angstrom=0.0,
        source_url=f"https://www.rcsb.org/structure/{structure.pdb_id}",
    )


def _reference_heavy_coordinates(mol: Chem.Mol) -> list[tuple[float, float, float]]:
    if mol.GetNumConformers() != 1:
        raise ValueError("reference molecule must contain exactly one conformer")
    conf = mol.GetConformer()
    coordinates: list[tuple[float, float, float]] = []
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() == 1:
            continue
        point = conf.GetAtomPosition(atom.GetIdx())
        coordinates.append((float(point.x), float(point.y), float(point.z)))
    if not coordinates:
        raise ValueError("reference molecule contains no heavy atoms")
    return coordinates


def _coordinate_identity(points: list[tuple[float, float, float]]) -> str:
    return sha256_json([[round(value, 6) for value in point] for point in points])


def _union_grid(points: list[tuple[float, float, float]]) -> dict[str, object]:
    if not points:
        raise ValueError("grid coordinate set is empty")
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
    payload = {
        "center": center,
        "size": sizes,
        "unclamped_size": required,
        "status": status,
        "reason": reason,
    }
    payload["grid_hash"] = sha256_json(payload)
    return payload


def _download_pdb(pdb_id: str, root: Path) -> tuple[Path, str]:
    path = root / "pdb" / f"{pdb_id}.pdb"
    if path.is_file():
        from research_os.core.hashing import sha256_file

        return path, sha256_file(path)
    digest = base._download(f"https://files.rcsb.org/download/{pdb_id}.pdb", path)
    return path, digest


def _download_reference(
    structure: crossdock001.SelectedStructure,
    ligand_auth_seq_id: int,
    target_name: str,
    root: Path,
) -> tuple[Path, Chem.Mol]:
    case = _provisional_case(structure, target_name)
    path = root / "reference" / f"{structure.pdb_id}-{structure.ligand_id}.sdf"
    base._download(base._instance_sdf_url(case, ligand_auth_seq_id), path)
    return path, base.load_single_sdf(path)


def preflight_directed_case(case: dict[str, object], root: Path) -> dict[str, object]:
    source = crossdock001.SelectedStructure(**dict(case["source"]))
    target = crossdock001.SelectedStructure(**dict(case["target"]))
    record: dict[str, object] = {
        "case_id": case["case_id"],
        "pair_id": case["pair_id"],
        "target_name": case["target_name"],
        "source": source.to_dict(),
        "target": target.to_dict(),
    }
    try:
        source_path, source_pdb_sha256 = _download_pdb(source.pdb_id, root)
        target_path, target_pdb_sha256 = _download_pdb(target.pdb_id, root)
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
        target_text = target_path.read_text(encoding="utf-8", errors="replace")
        record["source_pdb_sha256"] = source_pdb_sha256
        record["target_pdb_sha256"] = target_pdb_sha256

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
        if len(pairs) < crossdock001.MIN_ALIGNMENT_CA_PAIRS:
            raise ValueError(
                f"only {len(pairs)} identical aligned pocket CA pairs; "
                f"minimum is {crossdock001.MIN_ALIGNMENT_CA_PAIRS}"
            )
        transform = kabsch_source_to_target(pairs)
        if not math.isfinite(transform.rmsd_angstrom):
            raise ValueError("pocket alignment RMSD is non-finite")

        source_reference_path, source_reference = _download_reference(
            source,
            source_ligand.auth_seq_id,
            str(case["target_name"]),
            root,
        )
        target_reference_path, target_reference = _download_reference(
            target,
            target_ligand.auth_seq_id,
            str(case["target_name"]),
            root,
        )
        source_reference_xyz = _reference_heavy_coordinates(source_reference)
        target_reference_xyz = _reference_heavy_coordinates(target_reference)
        if len(source_reference_xyz) != len(source_ligand.heavy_xyz):
            raise ValueError("source reference heavy-atom count does not match source PDB ligand")
        if len(target_reference_xyz) != len(target_ligand.heavy_xyz):
            raise ValueError("target reference heavy-atom count does not match target PDB ligand")

        transformed_source_xyz = transform.apply(source_reference_xyz)
        grid = _union_grid(transformed_source_xyz + list(target_ligand.heavy_xyz))
        if grid["status"] != "PASS":
            raise ValueError(str(grid["reason"]))

        source_centroid = tuple(
            sum(point[axis] for point in transformed_source_xyz) / len(transformed_source_xyz)
            for axis in range(3)
        )
        target_centroid = tuple(
            sum(point[axis] for point in target_ligand.heavy_xyz) / len(target_ligand.heavy_xyz)
            for axis in range(3)
        )

        record.update(
            {
                "status": "ELIGIBLE",
                "source_chain_residues": len(source_residues),
                "target_chain_residues": len(target_residues),
                "target_pocket_residues": len(pocket),
                "matched_identical_pocket_ca_pairs": len(pairs),
                "alignment_rmsd_angstrom": transform.rmsd_angstrom,
                "rotation": transform.rotation,
                "translation": transform.translation,
                "source_reference_heavy_atoms": len(source_reference_xyz),
                "target_reference_heavy_atoms": len(target_reference_xyz),
                "source_reference_coordinate_hash": _coordinate_identity(source_reference_xyz),
                "transformed_source_reference_coordinate_hash": _coordinate_identity(transformed_source_xyz),
                "target_reference_coordinate_hash": _coordinate_identity(target_reference_xyz),
                "transformed_source_to_target_ligand_min_distance_angstrom": minimum_distance(
                    transformed_source_xyz, target_ligand.heavy_xyz
                ),
                "transformed_source_to_target_ligand_centroid_distance_angstrom": math.dist(
                    source_centroid, target_centroid
                ),
                "grid": grid,
                "source_reference_filename": source_reference_path.name,
                "target_reference_filename": target_reference_path.name,
            }
        )
    except Exception as exc:
        record["status"] = "INELIGIBLE"
        record["reason"] = str(exc)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Structurally preflight frozen CROSSDOCK-001 cases without Vina"
    )
    parser.add_argument("--workdir", default=".crossdock001-preflight")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if crossdock001.source_list_sha256() != crossdock001.SOURCE_LIST_SHA256:
        raise SystemExit("published cross-docking source-list identity changed")
    selected = crossdock001.selected_published_pairs()
    if tuple(pair.pair_id for pair in selected) != crossdock001.EXPECTED_SELECTED_PAIR_IDS:
        raise SystemExit("deterministic selected pair identity changed")
    if tuple(crossdock001.selection_key(pair) for pair in selected) != crossdock001.EXPECTED_SELECTION_KEYS:
        raise SystemExit("deterministic selected pair key changed")

    root = Path(args.workdir)
    root.mkdir(parents=True, exist_ok=True)
    records = [preflight_directed_case(case, root) for case in crossdock001.directed_case_specs()]
    manifest_payload = [
        {
            "case_id": record["case_id"],
            "pair_id": record["pair_id"],
            "source": record["source"],
            "target": record["target"],
            "source_pdb_sha256": record.get("source_pdb_sha256"),
            "target_pdb_sha256": record.get("target_pdb_sha256"),
            "matched_identical_pocket_ca_pairs": record.get("matched_identical_pocket_ca_pairs"),
            "alignment_rmsd_angstrom": record.get("alignment_rmsd_angstrom"),
            "rotation": record.get("rotation"),
            "translation": record.get("translation"),
            "transformed_source_reference_coordinate_hash": record.get(
                "transformed_source_reference_coordinate_hash"
            ),
            "grid": record.get("grid"),
            "status": record["status"],
            "reason": record.get("reason"),
        }
        for record in records
    ]
    eligible = sum(record["status"] == "ELIGIBLE" for record in records)
    report = {
        "benchmark_id": crossdock001.BENCHMARK_ID,
        "protocol_id": crossdock001.PROTOCOL_ID,
        "kind": "prospective-structural-preflight-no-docking",
        "source": {
            "name": crossdock001.SOURCE_NAME,
            "url": crossdock001.SOURCE_URL,
            "source_list_sha256": crossdock001.SOURCE_LIST_SHA256,
        },
        "selection_salt": crossdock001.SELECTION_SALT,
        "pair_count": crossdock001.TARGET_PAIR_COUNT,
        "directed_case_count": crossdock001.DIRECTED_CASE_COUNT,
        "pocket_cutoff_angstrom": crossdock001.POCKET_CUTOFF_ANGSTROM,
        "minimum_alignment_ca_pairs": crossdock001.MIN_ALIGNMENT_CA_PAIRS,
        "records": records,
        "eligible_count": eligible,
        "selection_manifest_hash": sha256_json(manifest_payload),
        "docking_executed": False,
        "vina_imported_or_invoked": False,
    }
    output = Path(args.output) if args.output else root / "crossdock001-preflight-v1.0.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if eligible == crossdock001.DIRECTED_CASE_COUNT else 1


if __name__ == "__main__":
    raise SystemExit(main())
