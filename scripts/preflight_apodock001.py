from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import time

from rdkit import Chem

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking import apodock001
from research_os.docking import redocking as base
from research_os.docking.crossdock_alignment import (
    kabsch_source_to_target,
    parse_protein_chain,
)
from research_os.docking.crossdock_identity import stable_hash


@dataclass(frozen=True)
class LigandComponents:
    coordinates: tuple[tuple[float, float, float], ...]
    auth_seq_ids: tuple[int, ...]
    component_heavy_atom_counts: tuple[int, ...]


def _download_with_retry(url: str, path: Path, *, attempts: int = 4) -> str:
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


def _download_pdb(pdb_id: str, root: Path) -> tuple[Path, str]:
    path = root / "pdb" / f"{pdb_id}.pdb"
    if path.is_file():
        return path, sha256_file(path)
    digest = _download_with_retry(f"https://files.rcsb.org/download/{pdb_id}.pdb", path)
    return path, digest


def _xyz(line: str) -> tuple[float, float, float]:
    return float(line[30:38]), float(line[38:46]), float(line[46:54])


def parse_ligand_components(
    pdb_text: str,
    *,
    component_ids: tuple[str, ...],
    author_chain: str,
) -> LigandComponents:
    grouped: dict[str, dict[tuple[int, str], list[tuple[float, float, float]]]] = {
        component_id: {} for component_id in component_ids
    }
    for line in pdb_text.splitlines():
        if len(line) < 54 or not base._primary_altloc(line):
            continue
        if line[:6].strip() != "HETATM" or line[21].strip() != author_chain:
            continue
        component_id = line[17:20].strip()
        if component_id not in grouped:
            continue
        if base._element_from_pdb_line(line) in {"H", "D"}:
            continue
        try:
            seq = int(line[22:26].strip())
        except ValueError:
            continue
        grouped[component_id].setdefault((seq, line[26].strip()), []).append(_xyz(line))

    coordinates: list[tuple[float, float, float]] = []
    seq_ids: list[int] = []
    heavy_counts: list[int] = []
    for component_id in component_ids:
        instances = grouped[component_id]
        if len(instances) != 1:
            raise ValueError(
                f"expected exactly one {component_id} instance on author chain "
                f"{author_chain}, found {len(instances)}"
            )
        (seq, _insertion), points = next(iter(instances.items()))
        if not points:
            raise ValueError(f"{component_id} contains no heavy atoms")
        seq_ids.append(seq)
        heavy_counts.append(len(points))
        coordinates.extend(points)
    return LigandComponents(tuple(coordinates), tuple(seq_ids), tuple(heavy_counts))


def _coordinate_identity(points: tuple[tuple[float, float, float], ...] | list[tuple[float, float, float]]) -> str:
    return sha256_json([[round(value, 6) for value in point] for point in points])


def _known_site_grid(points: list[tuple[float, float, float]]) -> dict[str, object]:
    if not points:
        raise ValueError("reference ligand coordinate set is empty")
    mins = [min(point[axis] for point in points) for axis in range(3)]
    maxs = [max(point[axis] for point in points) for axis in range(3)]
    center = [(low + high) / 2.0 for low, high in zip(mins, maxs)]
    spans = [high - low for low, high in zip(mins, maxs)]
    required = [
        span + 2.0 * apodock001.LIGAND_GRID_PADDING_ANGSTROM
        for span in spans
    ]
    sizes = [
        min(max(side, apodock001.GRID_MIN_SIDE_ANGSTROM), apodock001.GRID_MAX_SIDE_ANGSTROM)
        for side in required
    ]
    status = "PASS"
    reason = None
    if any(side > apodock001.GRID_MAX_SIDE_ANGSTROM for side in required):
        status = "OUT_OF_DOMAIN"
        reason = "transformed holo ligand requires a grid side larger than frozen 30 Å maximum"
    payload = {
        "protocol_id": apodock001.PROTOCOL_ID,
        "center": center,
        "size": sizes,
        "unclamped_size": required,
        "padding_angstrom": apodock001.LIGAND_GRID_PADDING_ANGSTROM,
        "status": status,
        "reason": reason,
    }
    payload["grid_hash"] = stable_hash(payload)
    return payload


def _provisional_holo_case(case: apodock001.ApoHoloCase, ligand_id: str) -> base.RedockingCase:
    return base.RedockingCase(
        case_id=f"PREFLIGHT-{case.case_id}",
        pdb_id=case.holo_pdb_id,
        ligand_id=ligand_id,
        ligand_author_chain=case.holo_ligand_author_chain,
        receptor_author_chains=(case.holo_receptor_author_chain,),
        target=case.receptor,
        resolution_angstrom=0.0,
        source_url=f"https://www.rcsb.org/structure/{case.holo_pdb_id}",
    )


def _single_component_reference(
    case: apodock001.ApoHoloCase,
    ligand: LigandComponents,
    root: Path,
) -> tuple[Path, Chem.Mol]:
    ligand_id = case.holo_ligand_components[0]
    provisional = _provisional_holo_case(case, ligand_id)
    path = root / "reference" / f"{case.holo_pdb_id}-{ligand_id}.sdf"
    _download_with_retry(base._instance_sdf_url(provisional, ligand.auth_seq_ids[0]), path)
    return path, base.load_single_sdf(path)


def _heavy_atom_count(mol: Chem.Mol) -> int:
    return sum(atom.GetAtomicNum() > 1 for atom in mol.GetAtoms())


def preflight_case(case: apodock001.ApoHoloCase, root: Path) -> dict[str, object]:
    record: dict[str, object] = {"case": case.to_dict()}
    try:
        apo_path, apo_sha = _download_pdb(case.apo_pdb_id, root)
        holo_path, holo_sha = _download_pdb(case.holo_pdb_id, root)
        apo_text = apo_path.read_text(encoding="utf-8", errors="replace")
        holo_text = holo_path.read_text(encoding="utf-8", errors="replace")
        record["apo_pdb_sha256"] = apo_sha
        record["holo_pdb_sha256"] = holo_sha

        apo_residues = parse_protein_chain(apo_text, case.apo_receptor_author_chain)
        holo_residues = parse_protein_chain(holo_text, case.holo_receptor_author_chain)
        ligand = parse_ligand_components(
            holo_text,
            component_ids=case.holo_ligand_components,
            author_chain=case.holo_ligand_author_chain,
        )
        pairs = apodock001.matched_global_ca_pairs(holo_residues, apo_residues)
        if len(pairs) < apodock001.MIN_GLOBAL_ALIGNMENT_CA_PAIRS:
            raise ValueError(
                f"only {len(pairs)} identical globally aligned CA pairs; minimum is "
                f"{apodock001.MIN_GLOBAL_ALIGNMENT_CA_PAIRS}"
            )
        transform = kabsch_source_to_target(pairs)
        if not math.isfinite(transform.rmsd_angstrom):
            raise ValueError("global holo-to-apo alignment RMSD is non-finite")

        transformed_reference = transform.apply(ligand.coordinates)
        grid = _known_site_grid(transformed_reference)
        if grid["status"] != "PASS":
            raise ValueError(str(grid["reason"]))

        chemistry_ready = False
        chemistry_note = (
            "branched glycan requires a covalent multi-component ligand adapter before Vina"
        )
        reference_filename = None
        if case.ligand_representation == "single_ccd":
            reference_path, reference = _single_component_reference(case, ligand, root)
            if _heavy_atom_count(reference) != len(ligand.coordinates):
                raise ValueError(
                    "RCSB instance SDF heavy-atom count does not match holo PDB ligand"
                )
            chemistry_ready = True
            chemistry_note = "single RCSB ligand instance SDF validated"
            reference_filename = reference_path.name
        elif case.ligand_representation != "branched_glycan":
            raise ValueError(f"unsupported ligand representation {case.ligand_representation!r}")

        record.update(
            {
                "status": "STRUCTURALLY_ELIGIBLE",
                "apo_chain_residues": len(apo_residues),
                "holo_chain_residues": len(holo_residues),
                "matched_identical_global_ca_pairs": len(pairs),
                "global_alignment_rmsd_angstrom": transform.rmsd_angstrom,
                "rotation": transform.rotation,
                "translation": transform.translation,
                "ligand_component_auth_seq_ids": ligand.auth_seq_ids,
                "ligand_component_heavy_atom_counts": ligand.component_heavy_atom_counts,
                "ligand_heavy_atoms": len(ligand.coordinates),
                "holo_reference_coordinate_hash": _coordinate_identity(ligand.coordinates),
                "transformed_holo_reference_coordinate_hash": _coordinate_identity(
                    transformed_reference
                ),
                "grid": grid,
                "chemistry_ready_for_vina": chemistry_ready,
                "chemistry_note": chemistry_note,
                "reference_filename": reference_filename,
            }
        )
    except Exception as exc:
        record["status"] = "STRUCTURALLY_INELIGIBLE"
        record["reason"] = str(exc)
        record["chemistry_ready_for_vina"] = False
    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preflight published APODOCK-001 apo/holo cases without Vina"
    )
    parser.add_argument("--workdir", default=".apodock001-preflight")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if apodock001.source_list_sha256() != apodock001.SOURCE_LIST_SHA256:
        raise SystemExit("published APODOCK source-list identity changed")
    if apodock001.case_metadata_sha256() != apodock001.CASE_METADATA_SHA256:
        raise SystemExit("frozen APODOCK case metadata changed")
    if len(apodock001.FROZEN_PUBLISHED_CASES) != apodock001.PUBLISHED_CASE_COUNT:
        raise SystemExit("published APODOCK case count changed")

    root = Path(args.workdir)
    root.mkdir(parents=True, exist_ok=True)
    records = [preflight_case(case, root) for case in apodock001.FROZEN_PUBLISHED_CASES]
    structural_eligible = sum(
        record["status"] == "STRUCTURALLY_ELIGIBLE" for record in records
    )
    chemistry_ready = sum(bool(record["chemistry_ready_for_vina"]) for record in records)

    manifest_payload = [
        {
            "case_id": record["case"]["case_id"],
            "apo_pdb_id": record["case"]["apo_pdb_id"],
            "holo_pdb_id": record["case"]["holo_pdb_id"],
            "ligand_components": record["case"]["holo_ligand_components"],
            "ligand_representation": record["case"]["ligand_representation"],
            "apo_pdb_sha256": record.get("apo_pdb_sha256"),
            "holo_pdb_sha256": record.get("holo_pdb_sha256"),
            "matched_identical_global_ca_pairs": record.get(
                "matched_identical_global_ca_pairs"
            ),
            "holo_reference_coordinate_hash": record.get(
                "holo_reference_coordinate_hash"
            ),
            "transformed_holo_reference_coordinate_hash": record.get(
                "transformed_holo_reference_coordinate_hash"
            ),
            "grid_hash": (record.get("grid") or {}).get("grid_hash"),
            "chemistry_ready_for_vina": record["chemistry_ready_for_vina"],
            "status": record["status"],
            "reason": record.get("reason"),
        }
        for record in records
    ]

    report = {
        "benchmark_id": apodock001.BENCHMARK_ID,
        "protocol_id": apodock001.PROTOCOL_ID,
        "kind": "prospective-structural-preflight-no-docking",
        "source": {
            "name": apodock001.SOURCE_NAME,
            "url": apodock001.SOURCE_URL,
            "source_list_sha256": apodock001.SOURCE_LIST_SHA256,
            "case_metadata_sha256": apodock001.CASE_METADATA_SHA256,
        },
        "published_case_count": apodock001.PUBLISHED_CASE_COUNT,
        "minimum_global_alignment_ca_pairs": apodock001.MIN_GLOBAL_ALIGNMENT_CA_PAIRS,
        "known_site_grid": {
            "padding_angstrom": apodock001.LIGAND_GRID_PADDING_ANGSTROM,
            "minimum_side_angstrom": apodock001.GRID_MIN_SIDE_ANGSTROM,
            "maximum_side_angstrom": apodock001.GRID_MAX_SIDE_ANGSTROM,
        },
        "records": records,
        "structurally_eligible_count": structural_eligible,
        "chemistry_ready_for_vina_count": chemistry_ready,
        "selection_manifest_hash": stable_hash(manifest_payload),
        "docking_executed": False,
        "vina_imported_or_invoked": False,
    }
    output = Path(args.output) if args.output else root / "apodock001-preflight-v1.0.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if structural_eligible == apodock001.PUBLISHED_CASE_COUNT else 1


if __name__ == "__main__":
    raise SystemExit(main())
