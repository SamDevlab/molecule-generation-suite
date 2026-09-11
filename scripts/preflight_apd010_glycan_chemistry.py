from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking import redocking as base
from research_os.docking.apodock_glycan import parse_glycan_atoms
from research_os.docking.apodock_glycan_chemistry import (
    NamedAtomKey,
    assemble_apd010_disaccharide,
    chemistry_identity,
    coordinate_mapping_diagnostic,
    load_named_ccd_mol2,
)
from research_os.docking.apodock_glycan_freeze import PDB_SHA256

COMPONENTS = ("BEM", "MAV")
PDB_ID = "1Y3N"
AUTHOR_CHAIN = "B"


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
    workdir.mkdir(parents=True, exist_ok=True)
    component_hashes: dict[str, str] = {}
    components: dict[str, Chem.Mol] = {}
    for component_id in COMPONENTS:
        path = workdir / f"{component_id}_ideal.mol2"
        url = f"https://files.rcsb.org/ligands/download/{component_id}_ideal.mol2"
        component_hashes[component_id] = _download_with_retry(url, path)
        if sha256_file(path) != component_hashes[component_id]:
            raise ValueError(f"{component_id} ideal MOL2 changed after download")
        components[component_id] = load_named_ccd_mol2(path, component_id)
        if components[component_id].GetNumHeavyAtoms() != 13:
            raise ValueError(f"{component_id} free CCD must contain 13 heavy atoms")

    assembled = assemble_apd010_disaccharide(components["BEM"], components["MAV"])

    pdb_path = workdir / f"{PDB_ID}.pdb"
    pdb_sha = _download_with_retry(f"https://files.rcsb.org/download/{PDB_ID}.pdb", pdb_path)
    if pdb_sha != PDB_SHA256:
        raise ValueError(f"frozen 1Y3N PDB changed: {pdb_sha} != {PDB_SHA256}")
    pdb_text = pdb_path.read_text(encoding="utf-8", errors="replace")
    observed = parse_glycan_atoms(
        pdb_text,
        component_ids=COMPONENTS,
        author_chain=AUTHOR_CHAIN,
    )
    observed_keys = [NamedAtomKey(atom.component_id, atom.atom_name) for atom in observed]
    mapping = coordinate_mapping_diagnostic(assembled, observed_keys)

    report: dict[str, object] = {
        "benchmark_id": "APODOCK-001",
        "case_id": "APD-010",
        "kind": "prospective-glycan-chemistry-preflight-no-docking",
        "component_ideal_mol2_sha256": component_hashes,
        "free_component_heavy_atoms": {
            component_id: components[component_id].GetNumHeavyAtoms()
            for component_id in COMPONENTS
        },
        "chemical_heavy_atoms": assembled.GetNumHeavyAtoms(),
        "chemical_formula": rdMolDescriptors.CalcMolFormula(assembled),
        "isomeric_smiles": Chem.MolToSmiles(assembled, canonical=True, isomericSmiles=True),
        "chemistry_identity": chemistry_identity(assembled),
        "coordinate_mapping": mapping,
        "frozen_link": {
            "donor": {"component_id": "BEM", "auth_seq_id": 2, "atom_name": "C1"},
            "acceptor": {"component_id": "MAV", "auth_seq_id": 1, "atom_name": "O4"},
        },
        "removed_donor_atom": {"component_id": "BEM", "atom_name": "O1"},
        "chemistry_ready_for_starting_conformer": True,
        "starting_conformer_generated": False,
        "docking_executed": False,
        "vina_imported_or_invoked": False,
    }
    report["report_identity"] = sha256_json(
        {key: value for key, value in report.items() if key != "report_identity"}
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", default=".apd010-glycan-chemistry")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    workdir = Path(args.workdir)
    report = inspect(workdir)
    output = Path(args.output) if args.output else workdir / "apd010-glycan-chemistry-v1.0.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
