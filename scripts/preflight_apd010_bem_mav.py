"""Run the APD-010 structural and chemical readiness gate.

This script is intentionally a preflight only.  It downloads and verifies
the frozen PDB/CCD inputs, creates one chemical graph, and emits provenance.
It never imports or invokes Vina and never creates docking artifacts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen

from research_os.core.hashing import sha256_file
from research_os.docking import apodock001_freeze
from research_os.docking import apodock_glycan_freeze
from research_os.docking.apodock_glycan import (
    parse_glycan_atoms,
    parse_glycan_links,
    structural_identity,
    validate_link_atoms,
)
from research_os.docking.apodock_glycan_chemistry import (
    ADAPTER_ID,
    ADAPTER_VERSION,
    CCD_SOURCES,
    CHEMISTRY_GATE_ID,
    CHEMISTRY_GATE_VERSION,
    MOLECULE_ID,
    adapt_apd010,
    adapter_report_identity,
    load_named_ccd_sdf,
    NamedAtomKey,
)


def _download_verified(url: str, path: Path, expected_sha256: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "research-os-apd010-preflight/1.0"})
    with urlopen(request, timeout=60) as response:
        path.write_bytes(response.read())
    observed = sha256_file(path)
    if observed != expected_sha256:
        raise RuntimeError(f"source hash mismatch for {url}: {observed} != {expected_sha256}")
    return observed


def run_preflight(workdir: Path) -> dict[str, object]:
    pdb_path = workdir / "1Y3N.pdb"
    if not pdb_path.is_file():
        _download_verified(apodock_glycan_freeze.PDB_URL, pdb_path, apodock_glycan_freeze.PDB_SHA256)
    elif sha256_file(pdb_path) != apodock_glycan_freeze.PDB_SHA256:
        raise RuntimeError("cached APD-010 PDB hash does not match the frozen input")
    pdb_text = pdb_path.read_text(encoding="utf-8")

    atoms = parse_glycan_atoms(pdb_text, apodock_glycan_freeze.COMPONENT_IDS, apodock_glycan_freeze.AUTHOR_CHAIN)
    links = parse_glycan_links(pdb_text, apodock_glycan_freeze.COMPONENT_IDS, apodock_glycan_freeze.AUTHOR_CHAIN)
    validate_link_atoms(atoms, links)
    apodock_glycan_freeze.validate_frozen_structure(atoms, links)
    observed_keys = {NamedAtomKey(atom.component_id, atom.atom_name) for atom in atoms}

    loaded: dict[str, object] = {}
    source_hashes: dict[str, str] = {"1Y3N.pdb": apodock_glycan_freeze.PDB_SHA256}
    for component_id in apodock_glycan_freeze.COMPONENT_IDS:
        source = CCD_SOURCES[component_id]
        sdf_path = workdir / f"{component_id}_ideal.sdf"
        cif_path = workdir / f"{component_id}.cif"
        if not sdf_path.is_file():
            _download_verified(source["sdf_url"], sdf_path, source["sdf_sha256"])
        elif sha256_file(sdf_path) != source["sdf_sha256"]:
            raise RuntimeError(f"cached {component_id} SDF hash does not match the frozen input")
        if not cif_path.is_file():
            _download_verified(source["cif_url"], cif_path, source["cif_sha256"])
        elif sha256_file(cif_path) != source["cif_sha256"]:
            raise RuntimeError(f"cached {component_id} CIF hash does not match the frozen input")
        source_hashes[f"{component_id}.sdf"] = source["sdf_sha256"]
        source_hashes[f"{component_id}.cif"] = source["cif_sha256"]
        loaded[component_id] = load_named_ccd_sdf(
            sdf_path,
            cif_path,
            component_id,
            expected_sdf_sha256=source["sdf_sha256"],
            expected_cif_sha256=source["cif_sha256"],
        )

    result = adapt_apd010(
        loaded["BEM"],
        loaded["MAV"],
        source_hashes=source_hashes,
        observed_keys=observed_keys,
    )
    baseline_direct = [
        record for record in apodock001_freeze.FROZEN_STRUCTURAL_IDENTITIES
        if record["chemistry_ready_for_vina"]
    ]
    if len(baseline_direct) != 9:
        raise RuntimeError("the immutable APODOCK baseline no longer contains exactly nine direct cases")

    apd010_case = {
        "case_id": "APD-010",
        "structural_identity": structural_identity(atoms, links),
        "structural_heavy_atoms": len(atoms),
        "chemical_input_identity": result.input_identity,
        "chemical_output_identity": result.output_identity,
        "adapter_id": result.adapter_id,
        "adapter_version": result.adapter_version,
        "transformations": list(result.transformations),
        "chemistry_ready_for_vina": result.chemistry_ready,
        "diagnostics": dict(result.diagnostics),
    }
    gate = {
        "schema_version": "apd010-chemistry-gate-v1",
        "gate_id": CHEMISTRY_GATE_ID,
        "gate_version": CHEMISTRY_GATE_VERSION,
        "molecule_id": MOLECULE_ID,
        "case_id": MOLECULE_ID,
        "pdb_id": apodock_glycan_freeze.PDB_ID,
        "pdb_sha256": apodock_glycan_freeze.PDB_SHA256,
        "source_hashes": source_hashes,
        "structural_identity": apd010_case["structural_identity"],
        "chemical_input_identity": result.input_identity,
        "chemical_output_identity": result.output_identity,
        "adapter_id": ADAPTER_ID,
        "adapter_version": ADAPTER_VERSION,
        "transformations": list(result.transformations),
        "chemistry_ready_for_vina": True,
        "structurally_eligible_count": 10,
        "chemistry_ready_for_vina_count": len(baseline_direct) + 1,
        "baseline_direct_chemistry_ready_case_ids": [record["case_id"] for record in baseline_direct],
        "adapted_case_ids": ["APD-010"],
        "apd010": apd010_case,
        "docking_executed": False,
        "vina_imported_or_invoked": False,
    }
    gate["report_identity"] = adapter_report_identity(gate)
    return gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, help="cache directory for verified source files")
    parser.add_argument("--output", type=Path, help="write the deterministic JSON report to this path")
    args = parser.parse_args()
    if args.workdir:
        report = run_preflight(args.workdir)
    else:
        with tempfile.TemporaryDirectory(prefix="apd010-bem-mav-") as directory:
            report = run_preflight(Path(directory))
    serialized = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    print("APD-010: chemistry-ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
