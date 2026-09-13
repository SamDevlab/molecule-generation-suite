"""Produce the APD-007 postmortem diagnostic without rerunning Vina."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from rdkit import Chem

from research_os.docking.apodock001_analysis import (
    build_transformed_reference,
    same_frame_symmetry_aware_rmsd,
)
from research_os.docking.apodock001_future import normalize_openbabel_pose_for_reference


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs" / "apodock001-v1.0.2"
OUT = ROOT / "postmortem" / "APD-007-diagnostic-analysis.json"


def sha256(path: Path) -> str:
    # The repository is checked out on Windows with CRLF conversion.  The
    # sealed Linux bytes are the canonical LF form; this normalization is
    # in-memory/diagnostic-only and never writes to the historical run.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> None:
    raw = RUN / "raw" / "APD-007" / "vina_poses.pdbqt"
    derived_sdf = RUN / "analysis-derived" / "APD-007" / "pose_01.sdf"
    seal = json.loads((RUN / "raw-results-seal.json").read_text(encoding="utf-8"))
    protocol = json.loads(
        (ROOT / "configs" / "apodock001-protocol-freeze-v1.0.2.json").read_text(
            encoding="utf-8"
        )
    )
    case = next(item for item in protocol["benchmark"]["cases"] if item["case_id"] == "APD-007")
    raw_hash = sha256(raw)
    if raw_hash != seal["raw_output_hashes"]["APD-007"]:
        raise SystemExit("historical APD-007 raw hash mismatch")
    historical_supplier = Chem.SDMolSupplier(str(derived_sdf), removeHs=False, sanitize=True)
    historical_sanitize_failed = len(historical_supplier) == 1 and historical_supplier[0] is None
    temporary = tempfile.TemporaryDirectory(prefix="apodock001-apd007-")
    try:
        bundle = Path(temporary.name) / "bundle"
        shutil.copytree(ROOT / "inputs" / "apodock001" / "v1.0.2", bundle)
        for path in bundle.rglob("*"):
            if path.is_file():
                path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
        reference = build_transformed_reference(protocol, bundle, case).molecule
        if reference is None:
            raise SystemExit("APD-007 frozen reference could not be built")
        repaired, mapping = normalize_openbabel_pose_for_reference(derived_sdf, reference)
        diagnostic_rmsd = same_frame_symmetry_aware_rmsd(reference, repaired)
    finally:
        temporary.cleanup()
    report = {
        "schema_version": "research-os.apodock001.apd007-postmortem-diagnostic.v1",
        "status": "POSTMORTEM_DIAGNOSTIC_ONLY",
        "historical_case_status": "INDETERMINATE",
        "historical_first_loss": "POSE_CONVERSION_FAILED",
        "source_raw_path": "runs/apodock001-v1.0.2/raw/APD-007/vina_poses.pdbqt",
        "source_raw_sha256": raw_hash,
        "returned_models": sum(line.startswith("MODEL") for line in raw.read_text(encoding="utf-8").splitlines()),
        "historical_derived_sdf_path": "runs/apodock001-v1.0.2/analysis-derived/APD-007/pose_01.sdf",
        "historical_derived_sdf_sha256": sha256(derived_sdf),
        "historical_rdkit_sanitize_failed": historical_sanitize_failed,
        "failure_stage": "RDKit sanitization of Open Babel SDF",
        "failure_reason": "Explicit valence for atom #1 N, 4, is greater than permitted; SDF omits the formal positive charge.",
        "future_adapter": {
            "strategy": "remove explicit hydrogens, match the heavy-atom graph to the frozen reference, copy frozen formal charges, sanitize, and preserve coordinates",
            "mapping_length": len(mapping),
            "diagnostic_status": diagnostic_rmsd.status,
            "diagnostic_same_frame_rmsd_angstrom": diagnostic_rmsd.rmsd_angstrom,
            "reference_heavy_atoms": diagnostic_rmsd.reference_heavy_atoms,
            "predicted_heavy_atoms": diagnostic_rmsd.predicted_heavy_atoms,
        },
        "historical_manifest_rewritten": False,
        "historical_primary_and_secondary_unchanged": True,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
