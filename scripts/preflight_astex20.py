from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.core.hashing import sha256_json
from research_os.docking import astex20
from research_os.docking import redocking as base
from research_os.docking import redocking_v12 as evaluator


def preflight_candidate(complex_id: str, rank: int, root: Path) -> dict[str, object]:
    pdb_id, ligand_id = astex20.split_complex_id(complex_id)
    candidate_dir = root / f"candidate-{rank:02d}-{pdb_id}-{ligand_id}"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    record: dict[str, object] = {
        "complex_id": complex_id,
        "selection_rank": rank,
        "selection_key_sha256": astex20.selection_rank_key(complex_id),
        "pdb_id": pdb_id,
        "ligand_id": ligand_id,
    }

    try:
        raw_path = candidate_dir / f"{pdb_id}.pdb"
        record["raw_pdb_sha256"] = base._download(
            f"https://files.rcsb.org/download/{pdb_id}.pdb",
            raw_path,
        )
        pdb_text = raw_path.read_text(encoding="utf-8", errors="replace")
        structural = astex20.discover_structural_case(pdb_text, pdb_id, ligand_id)
        record.update(structural)

        provisional = base.RedockingCase(
            case_id=f"PREFLIGHT-{rank:03d}",
            pdb_id=pdb_id,
            ligand_id=ligand_id,
            ligand_author_chain=str(structural["ligand_author_chain"]),
            receptor_author_chains=tuple(str(item) for item in structural["receptor_author_chains"]),
            target=str(structural["target"]),
            resolution_angstrom=float(structural["resolution_angstrom"]),
            source_url=str(structural["source_url"]),
        )
        extraction = base.extract_case_from_pdb(pdb_text, provisional)
        if extraction.ligand_auth_seq_id != int(structural["ligand_auth_seq_id"]):
            raise ValueError("discovery/extraction ligand auth_seq_id mismatch")

        reference_sdf = candidate_dir / "native_reference.sdf"
        reference_url = base._instance_sdf_url(provisional, extraction.ligand_auth_seq_id)
        record["reference_sdf_sha256"] = base._download(reference_url, reference_sdf)
        reference = base.load_single_sdf(reference_sdf)
        record["reference_heavy_atoms"] = reference.GetNumHeavyAtoms()
        if reference.GetNumHeavyAtoms() != extraction.ligand_heavy_atoms:
            raise ValueError("RCSB reference heavy-atom count does not match PDB ligand instance")

        grid = evaluator.derive_redocking_grid(reference)
        record["grid_status"] = grid.status
        record["grid_unclamped_size_angstrom"] = [
            grid.unclamped_size_x,
            grid.unclamped_size_y,
            grid.unclamped_size_z,
        ]
        if grid.status != "PASS":
            raise ValueError(grid.reason or "native-centered grid is outside frozen domain")
        record["status"] = "ELIGIBLE"
    except Exception as exc:
        record["status"] = "INELIGIBLE"
        record["reason"] = str(exc)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select and structurally preflight the prospective Astex-20 extension without docking"
    )
    parser.add_argument("--workdir", default=".astex20-preflight")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if astex20.source_list_sha256() != astex20.SOURCE_LIST_SHA256:
        raise SystemExit("frozen Astex 85 source-list identity changed")
    candidates = astex20.ranked_unseen_candidates()
    if candidates[:15] != astex20.INITIAL_HASH_RANKED_15:
        raise SystemExit("hash-ranked Astex selection identity changed")

    root = Path(args.workdir)
    root.mkdir(parents=True, exist_ok=True)
    selected: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    screened: list[dict[str, object]] = []

    for rank, complex_id in enumerate(candidates, start=1):
        record = preflight_candidate(complex_id, rank, root)
        screened.append(record)
        if record["status"] == "ELIGIBLE":
            selected_record = dict(record)
            selected_record["case_id"] = f"ATX-{len(selected) + 1:03d}"
            selected.append(selected_record)
            if len(selected) == astex20.TARGET_PROSPECTIVE_COUNT:
                break
        else:
            rejected.append(record)

    selection_payload = [
        {
            "case_id": record["case_id"],
            "complex_id": record["complex_id"],
            "selection_rank": record["selection_rank"],
            "pdb_id": record["pdb_id"],
            "ligand_id": record["ligand_id"],
            "ligand_author_chain": record["ligand_author_chain"],
            "receptor_author_chains": record["receptor_author_chains"],
            "resolution_angstrom": record["resolution_angstrom"],
        }
        for record in selected
    ]
    report = {
        "benchmark_id": astex20.BENCHMARK_ID,
        "protocol_id": astex20.PROTOCOL_ID,
        "kind": "prospective-structural-selection-preflight-no-docking",
        "source_set": astex20.SOURCE_SET,
        "source_list_url": astex20.SOURCE_LIST_URL,
        "source_list_sha256": astex20.SOURCE_LIST_SHA256,
        "selection_salt": astex20.SELECTION_SALT,
        "contact_cutoff_angstrom": astex20.CONTACT_CUTOFF_ANGSTROM,
        "prior_observed_astex": list(astex20.PRIOR_OBSERVED_ASTEX),
        "eligible_pool_before_structural_screening": len(candidates),
        "target_prospective_count": astex20.TARGET_PROSPECTIVE_COUNT,
        "selected_count": len(selected),
        "selected": selected,
        "rejected_before_cohort_filled": rejected,
        "screened_count": len(screened),
        "selection_manifest_hash": sha256_json(selection_payload),
        "docking_executed": False,
        "vina_imported_or_invoked": False,
    }
    output = Path(args.output) if args.output else root / "astex20-preflight-v1.0.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))

    if len(selected) != astex20.TARGET_PROSPECTIVE_COUNT:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
