from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking import apodock001, apodock001_freeze
from research_os.docking import redocking as base
from research_os.docking.apodock_glycan import (
    parse_glycan_atoms,
    parse_glycan_links,
    structural_identity,
    validate_link_atoms,
)

CASE_ID = "APD-010"
PDB_ID = "1Y3N"
COMPONENT_IDS = ("BEM", "MAV")
AUTHOR_CHAIN = "B"
EXPECTED_COMPONENT_HEAVY_COUNTS = {"BEM": 11, "MAV": 13}
EXPECTED_TOTAL_HEAVY_ATOMS = 24
EXPECTED_INTER_COMPONENT_LINKS = 1


def _frozen_case() -> apodock001.ApoHoloCase:
    return next(case for case in apodock001.FROZEN_PUBLISHED_CASES if case.case_id == CASE_ID)


def _frozen_identity() -> dict[str, object]:
    return next(row for row in apodock001_freeze.FROZEN_STRUCTURAL_IDENTITIES if row["case_id"] == CASE_ID)


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


def inspect(workdir: Path) -> dict[str, object]:
    case = _frozen_case()
    frozen = _frozen_identity()
    if case.holo_pdb_id != PDB_ID or case.holo_ligand_components != COMPONENT_IDS:
        raise ValueError("APD-010 frozen case identity changed")
    if case.holo_ligand_author_chain != AUTHOR_CHAIN or case.ligand_representation != "branched_glycan":
        raise ValueError("APD-010 frozen glycan representation changed")

    pdb_path = workdir / f"{PDB_ID}.pdb"
    pdb_sha = _download_with_retry(f"https://files.rcsb.org/download/{PDB_ID}.pdb", pdb_path)
    if pdb_sha != frozen["holo_pdb_sha256"]:
        raise ValueError(
            f"1Y3N PDB identity changed: {pdb_sha} != {frozen['holo_pdb_sha256']}"
        )
    if sha256_file(pdb_path) != pdb_sha:
        raise ValueError("downloaded 1Y3N PDB changed after hashing")

    pdb_text = pdb_path.read_text(encoding="utf-8", errors="replace")
    atoms = parse_glycan_atoms(
        pdb_text,
        component_ids=COMPONENT_IDS,
        author_chain=AUTHOR_CHAIN,
    )
    links = parse_glycan_links(
        pdb_text,
        component_ids=COMPONENT_IDS,
        author_chain=AUTHOR_CHAIN,
    )
    validate_link_atoms(atoms, links)

    component_counts = {
        component_id: sum(atom.component_id == component_id for atom in atoms)
        for component_id in COMPONENT_IDS
    }
    if component_counts != EXPECTED_COMPONENT_HEAVY_COUNTS:
        raise ValueError(
            f"APD-010 component heavy-atom inventory changed: {component_counts}"
        )
    if len(atoms) != EXPECTED_TOTAL_HEAVY_ATOMS:
        raise ValueError(f"APD-010 expected 24 glycan heavy atoms, found {len(atoms)}")
    if len(links) != EXPECTED_INTER_COMPONENT_LINKS:
        raise ValueError(
            f"APD-010 expected exactly one inter-component LINK, found {len(links)}"
        )
    first, second = links[0].canonical_endpoints()
    if {first.component_id, second.component_id} != set(COMPONENT_IDS):
        raise ValueError("APD-010 LINK does not connect BEM and MAV")

    atom_inventory = [atom.stable_dict() for atom in atoms]
    link_inventory = [link.stable_dict() for link in links]
    report: dict[str, object] = {
        "benchmark_id": apodock001.BENCHMARK_ID,
        "protocol_id": apodock001.PROTOCOL_ID,
        "kind": "apd010-remediated-glycan-structural-preflight-no-docking",
        "case_id": CASE_ID,
        "pdb_id": PDB_ID,
        "pdb_sha256": pdb_sha,
        "author_chain": AUTHOR_CHAIN,
        "component_ids": list(COMPONENT_IDS),
        "component_heavy_atom_counts": component_counts,
        "total_heavy_atoms": len(atoms),
        "atoms": atom_inventory,
        "links": link_inventory,
        "glycan_structural_identity": structural_identity(atoms, links),
        "adapter_implemented": False,
        "chemistry_ready_for_vina": False,
        "docking_executed": False,
        "vina_imported_or_invoked": False,
    }
    report["report_identity"] = sha256_json(
        {
            key: value
            for key, value in report.items()
            if key != "report_identity"
        }
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", default=".apd010-glycan-preflight")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    report = inspect(workdir)
    output = Path(args.output) if args.output else workdir / "apd010-glycan-preflight-v1.0.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
