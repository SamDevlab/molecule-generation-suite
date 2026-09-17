from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.docking import redocking as base
from research_os.docking import redocking_v12 as evaluator
from research_os.docking.redocking_holdout import FROZEN_HOLDOUT_CASES, PROTOCOL_ID


def preflight_case(case, root: Path) -> dict[str, object]:
    case_dir = root / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {
        "case_id": case.case_id,
        "pdb_id": case.pdb_id,
        "ligand_id": case.ligand_id,
        "ligand_author_chain": case.ligand_author_chain,
        "receptor_author_chains": list(case.receptor_author_chains),
    }

    try:
        raw_path = case_dir / f"{case.pdb_id}.pdb"
        result["raw_pdb_sha256"] = base._download(
            f"https://files.rcsb.org/download/{case.pdb_id}.pdb",
            raw_path,
        )
        extraction = base.extract_case_from_pdb(
            raw_path.read_text(encoding="utf-8", errors="replace"),
            case,
        )
        result["ligand_auth_seq_id"] = extraction.ligand_auth_seq_id
        result["ligand_insertion_code"] = extraction.ligand_insertion_code
        result["ligand_heavy_atoms_from_pdb"] = extraction.ligand_heavy_atoms
        result["receptor_atom_count"] = extraction.receptor_atom_count

        reference_sdf = case_dir / "native_reference.sdf"
        reference_url = base._instance_sdf_url(case, extraction.ligand_auth_seq_id)
        base._download(reference_url, reference_sdf)
        reference = base.load_single_sdf(reference_sdf)
        result["reference_heavy_atoms"] = reference.GetNumHeavyAtoms()
        if reference.GetNumHeavyAtoms() != extraction.ligand_heavy_atoms:
            raise ValueError(
                "RCSB reference heavy-atom count does not match the frozen PDB ligand instance"
            )

        grid = evaluator.derive_redocking_grid(reference)
        result["grid_status"] = grid.status
        result["grid_unclamped_size_angstrom"] = [
            grid.unclamped_size_x,
            grid.unclamped_size_y,
            grid.unclamped_size_z,
        ]
        result["status"] = "PASS"
        if grid.status != "PASS":
            result["status"] = grid.status
            result["reason"] = grid.reason
    except Exception as exc:
        result["status"] = "METADATA_ERROR"
        result["reason"] = str(exc)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate REDOCK-002 structure/ligand metadata without running docking"
    )
    parser.add_argument("--workdir", default=".redocking-holdout-preflight")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    root = Path(args.workdir)
    root.mkdir(parents=True, exist_ok=True)
    records = [preflight_case(case, root) for case in FROZEN_HOLDOUT_CASES]
    report = {
        "protocol_id": PROTOCOL_ID,
        "kind": "structural-preflight-no-docking",
        "total_cases": len(records),
        "records": records,
    }
    output = Path(args.output) if args.output else root / "preflight-redock-002.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))

    if any(record["status"] == "METADATA_ERROR" for record in records):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
