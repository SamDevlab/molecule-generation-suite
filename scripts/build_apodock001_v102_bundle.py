"""Materialize and hash the reviewed APODOCK-001 v1.0.2 input bundle.

The script is intentionally explicit about the nine audited instance SDFs. It
does not download anything; all source bytes must already be present locally.
It writes the bundle manifest and derives the v1.0.2 protocol identity from
that manifest, leaving v1.0.1 untouched.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from research_os.core.hashing import sha256_file, sha256_json


V101_PROTOCOL = Path("configs/apodock001-protocol-freeze-v1.0.1.json")
EXPECTED_AUDIT_CLASSIFICATIONS = {"BYTE_MATCH", "REPRESENTATION_DRIFT"}
CASE_IDS = tuple(f"APD-{index:03d}" for index in range(1, 10))
APO_HOLO = {
    "APD-001": ("1FTO", "1FTM"),
    "APD-002": ("1JEJ", "1JG6"),
    "APD-003": ("1GUD", "1RPJ"),
    "APD-004": ("1URP", "2DRI"),
    "APD-005": ("1USG", "1USI"),
    "APD-006": ("1RF5", "1RF4"),
    "APD-007": ("1SW5", "1SW2"),
    "APD-008": ("1EX6", "1EX7"),
    "APD-009": ("2E2N", "2E2O"),
}
CCD_SOURCES = {
    "BEM_ideal.sdf": ("BEM", "https://files.rcsb.org/ligands/download/BEM_ideal.sdf"),
    "BEM.cif": ("BEM", "https://files.rcsb.org/ligands/download/BEM.cif"),
    "MAV_ideal.sdf": ("MAV", "https://files.rcsb.org/ligands/download/MAV_ideal.sdf"),
    "MAV.cif": ("MAV", "https://files.rcsb.org/ligands/download/MAV.cif"),
}


def _file_record(
    root: Path,
    logical_name: str,
    *,
    source_url: str,
    source_database: str,
    retrieval_provenance: str,
    case_id: str | None,
    role: str,
    scientific_identity: dict[str, Any],
) -> dict[str, Any]:
    path = root / logical_name
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(path)
    return {
        "logical_name": logical_name,
        "source_url": source_url,
        "source_database": source_database,
        "retrieval_provenance": retrieval_provenance,
        "case_id": case_id,
        "role": role,
        "sha256": sha256_file(path),
        "scientific_identity": scientific_identity,
    }


def build(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(args.bundle_root)
    protocol_v101 = json.loads(Path(args.protocol_v101).read_text(encoding="utf-8"))
    audit = json.loads(Path(args.audit_report).read_text(encoding="utf-8"))
    if audit["summary"]["classifications"] != {"REPRESENTATION_DRIFT": 9}:
        raise ValueError("v1.0.2 requires all nine audit classifications to be REPRESENTATION_DRIFT")
    if not audit["summary"]["all_nine_scientifically_equivalent"]:
        raise ValueError("audit did not prove all nine current inputs scientifically equivalent")

    audit_by_case = {record["case_id"]: record for record in audit["records"]}
    protocol_cases = {case["case_id"]: case for case in protocol_v101["benchmark"]["cases"]}
    files: list[dict[str, Any]] = []
    for case_id in CASE_IDS:
        case = protocol_cases[case_id]
        audit_record = audit_by_case[case_id]
        filename = case["reference_filename"]
        current_identity = audit_record["current_identity"]
        coordinate = audit_record["coordinate_comparison"]
        files.append(
            _file_record(
                root,
                f"reference-sdf/{filename}",
                source_url=audit_record["url"],
                source_database="RCSB ModelServer instance SDF",
                retrieval_provenance="three-download provenance audit; selected attempt-1 bytes; workflow 34642755042 historical URL reconstructed from fa0a737eaa1989856474068f330c3c2c52d74344",
                case_id=case_id,
                role="single_ccd_reference_ligand_sdf",
                scientific_identity={
                    "component_id": audit_record["ccd_id"],
                    "formula": current_identity["formula"],
                    "heavy_atom_count": current_identity["heavy_atom_count"],
                    "formal_charge": current_identity["formal_charge"],
                    "element_counts": current_identity["element_counts"],
                    "canonical_smiles": current_identity["canonical_smiles"],
                    "canonical_isomeric_smiles": current_identity["canonical_isomeric_smiles"],
                    "coordinate_identity": coordinate["mapped_coordinate_hash"],
                    "same_frame_rmsd_angstrom": coordinate["rmsd_angstrom"],
                    "same_frame_max_delta_angstrom": coordinate["max_delta_angstrom"],
                },
            )
        )
        apo_id, holo_id = APO_HOLO[case_id]
        files.append(
            _file_record(
                root,
                f"pdb/{apo_id}.pdb",
                source_url=f"https://files.rcsb.org/download/{apo_id}.pdb",
                source_database="RCSB PDB",
                retrieval_provenance="frozen structural preflight artifact 10280154166 / workflow 34642755042",
                case_id=case_id,
                role="apo_receptor_source",
                scientific_identity={"pdb_id": apo_id, "pdb_sha256": case["apo_pdb_sha256"]},
            )
        )
        files.append(
            _file_record(
                root,
                f"pdb/{holo_id}.pdb",
                source_url=f"https://files.rcsb.org/download/{holo_id}.pdb",
                source_database="RCSB PDB",
                retrieval_provenance="frozen structural preflight artifact 10280154166 / workflow 34642755042",
                case_id=case_id,
                role="holo_reference_structure",
                scientific_identity={
                    "pdb_id": holo_id,
                    "pdb_sha256": case["holo_pdb_sha256"],
                    "holo_reference_coordinate_hash": case["holo_reference_coordinate_hash"],
                },
            )
        )

    apd010_case = protocol_cases["APD-010"]
    for pdb_id, role in (
        (apd010_case["apo_pdb_id"], "apo_receptor_source"),
        (apd010_case["holo_pdb_id"], "holo_reference_structure"),
    ):
        files.append(
            _file_record(
                root,
                f"pdb/{pdb_id}.pdb",
                source_url=f"https://files.rcsb.org/download/{pdb_id}.pdb",
                source_database="RCSB PDB",
                retrieval_provenance="frozen structural preflight artifact 10280154166 / workflow 34642755042",
                case_id="APD-010",
                role=role,
                scientific_identity={
                    "pdb_id": pdb_id,
                    "pdb_sha256": apd010_case["apo_pdb_sha256"] if pdb_id == apd010_case["apo_pdb_id"] else apd010_case["holo_pdb_sha256"],
                    **(
                        {"holo_reference_coordinate_hash": apd010_case["holo_reference_coordinate_hash"]}
                        if pdb_id == apd010_case["holo_pdb_id"]
                        else {}
                    ),
                },
            )
        )

    for filename, (component_id, url) in CCD_SOURCES.items():
        files.append(
            _file_record(
                root,
                f"apd010/{filename}",
                source_url=url,
                source_database="RCSB Chemical Component Dictionary",
                retrieval_provenance="frozen APD-010 chemistry gate v1.0.0; source hashes already committed in v1.0.1",
                case_id="APD-010",
                role="apd010_ccd_source",
                scientific_identity={
                    "component_id": component_id,
                    "adapter_id": "research-os.apd010.bem-mav",
                    "adapter_version": "1.0.0",
                },
            )
        )
    gate_path = root / "apd010/chemistry-gate.json"
    files.append(
        _file_record(
            root,
            "apd010/chemistry-gate.json",
            source_url="repository://.run-apd010-inputs/gate.json",
            source_database="Research OS APD-010 chemistry gate",
            retrieval_provenance="local preflight report generated before any docking; report asserts docking_executed=false",
            case_id="APD-010",
            role="apd010_chemistry_gate_report",
            scientific_identity={
                "adapter_id": "research-os.apd010.bem-mav",
                "adapter_version": "1.0.0",
                "output_identity": protocol_v101["chemistry"]["apd010"]["output_identity"],
            },
        )
    )

    files.sort(key=lambda item: item["logical_name"])
    bundle_payload = {
        "schema_version": "research-os.apodock001.input-bundle.v1",
        "benchmark_id": "APODOCK-001",
        "protocol_lineage": "research-os.apodock001.protocol.v1.0.1+9e293289c9729603",
        "case_order": list(CASE_IDS) + ["APD-010"],
        "chemistry_gate": {
            "ready_count": 10,
            "apd010_adapter_id": "research-os.apd010.bem-mav",
            "apd010_adapter_version": "1.0.0",
        },
        "files": files,
    }
    bundle_hash = sha256_json(bundle_payload)
    bundle_id = f"research-os.apodock001.input-bundle.v1+{bundle_hash[:16]}"
    manifest = {
        **bundle_payload,
        "bundle_hash": bundle_hash,
        "bundle_id": bundle_id,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    protocol = deepcopy(protocol_v101)
    protocol["protocol_version"] = "1.0.2"
    protocol["input_bundle"] = {
        "schema_version": manifest["schema_version"],
        "bundle_id": bundle_id,
        "bundle_hash": bundle_hash,
        "manifest_logical_name": "manifest.json",
        "offline_required": True,
    }
    for case in protocol["benchmark"]["cases"]:
        if case["case_id"] in audit_by_case:
            filename = case["reference_filename"]
            bundle_file = next(item for item in files if item["logical_name"] == f"reference-sdf/{filename}")
            case["reference_sdf_sha256"] = bundle_file["sha256"]
    protocol["evidence"]["required_bundle"].append("frozen input bundle manifest and bytes")
    scientific_payload = {
        key: value
        for key, value in protocol.items()
        if key not in {"schema_version", "protocol_id", "protocol_hash", "operational_metadata"}
    }
    protocol_hash = sha256_json(scientific_payload)
    protocol["protocol_hash"] = protocol_hash
    protocol["protocol_id"] = f"research-os.apodock001.protocol.v1.0.2+{protocol_hash[:16]}"
    Path(args.protocol_output).write_text(json.dumps(protocol, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest, protocol


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-root", default="inputs/apodock001/v1.0.2")
    parser.add_argument("--audit-report", default="docs/apodock001-sdf-provenance-audit-v1.0.1.json")
    parser.add_argument("--protocol-v101", default=str(V101_PROTOCOL))
    parser.add_argument("--protocol-output", default="configs/apodock001-protocol-freeze-v1.0.2.json")
    args = parser.parse_args()
    manifest, protocol = build(args)
    print(json.dumps({
        "bundle_id": manifest["bundle_id"],
        "bundle_hash": manifest["bundle_hash"],
        "protocol_id": protocol["protocol_id"],
        "protocol_hash": protocol["protocol_hash"],
        "file_count": len(manifest["files"]),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
