"""Run the APODOCK-001 v1.0.2 preflight entirely from frozen local bytes."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import tempfile

from rdkit import Chem

from research_os.core.hashing import sha256_file, sha256_json
from research_os.docking.apodock001_execution import (
    APODOCK001ExecutionAdapter,
    build_environment_manifest,
    build_evidence_scaffold,
)
from research_os.docking.apodock001_input_bundle import verify_frozen_input_bundle
from research_os.docking.apodock001_protocol import load_and_validate_v102


def _load_one(path: Path) -> Chem.Mol:
    molecules = [mol for mol in Chem.SDMolSupplier(str(path), removeHs=False, sanitize=True) if mol is not None]
    if len(molecules) != 1 or molecules[0].GetNumConformers() != 1:
        raise ValueError(f"offline frozen SDF is not one valid conformer: {path}")
    return molecules[0]


def run(args: argparse.Namespace) -> dict[str, object]:
    protocol = load_and_validate_v102(args.protocol)
    bundle_root = Path(args.bundle_root)
    bundle = verify_frozen_input_bundle(protocol, bundle_root)
    records = {record["logical_name"]: record for record in bundle["files"]}
    chemistry_records = []
    for case in protocol["benchmark"]["cases"]:
        if case["case_id"] == "APD-010":
            continue
        logical_name = f"reference-sdf/{case['reference_filename']}"
        molecule = _load_one(bundle_root / logical_name)
        identity = records[logical_name]["scientific_identity"]
        if molecule.GetNumHeavyAtoms() != identity["heavy_atom_count"]:
            raise ValueError(f"offline chemistry identity changed for {case['case_id']}")
        chemistry_records.append(case["case_id"])
    gate = json.loads((bundle_root / "apd010/chemistry-gate.json").read_text(encoding="utf-8"))
    if gate.get("chemistry_ready_for_vina") is not True or gate.get("chemistry_ready_for_vina_count") != 10:
        raise ValueError("offline APD-010 chemistry gate is not 10/10")
    if gate.get("docking_executed") is not False or gate.get("vina_imported_or_invoked") is not False:
        raise ValueError("offline APD-010 gate reports an execution")

    with tempfile.TemporaryDirectory(prefix="apodock001-v102-offline-") as directory:
        root = Path(directory)
        adapter = APODOCK001ExecutionAdapter(
            args.protocol,
            source_root=bundle_root,
            run_root=root / "future-run",
            staging_root=root / "prepared-staging",
            git_sha=args.git_sha,
        )
        preflight = adapter.preflight()
        prepared = {}
        source_root = root / "synthetic-prepared"
        for case in adapter.plan.cases:
            prepared[case.case_id] = {}
            for kind in ("receptor", "ligand"):
                path = source_root / case.case_id / f"{kind}.pdbqt"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"offline prepared fixture {case.case_id} {kind}\n".encode())
                prepared[case.case_id][kind] = {
                    "case_id": case.case_id,
                    "artifact_kind": kind,
                    "source_hashes": deepcopy(case.input_hashes),
                    "chemistry": deepcopy(case.chemistry),
                    "preparation": deepcopy(case.preparation[kind]),
                    "output_path": str(path),
                    "output_sha256": sha256_file(path),
                    "expected_destination": getattr(case, f"{kind}_prepared_output"),
                    "protocol_id": adapter.plan.protocol_id,
                    "planned_run_id": adapter.plan.planned_run_id,
                }
        staged = adapter.stage_prepared_artifacts(prepared)
        adapter.verify_staged_artifacts(staged)
        adapter.verify_execution_manifest()
        environment = build_environment_manifest(
            protocol_id=adapter.plan.protocol_id,
            git_sha=args.git_sha,
            vina=None,
            openbabel=None,
        )
        scaffold = build_evidence_scaffold(adapter.plan, git_sha=args.git_sha, environment=environment)
        if adapter.run_root.exists():
            raise ValueError("offline preflight unexpectedly created a prospective run directory")

    report = {
        "status": "READY_FOR_EXPLICIT_AUTHORIZATION",
        "mode": "offline_frozen_input_bundle_preflight",
        "protocol_id": protocol["protocol_id"],
        "protocol_hash": protocol["protocol_hash"],
        "bundle_id": bundle["bundle_id"],
        "bundle_hash": bundle["bundle_hash"],
        "planned_run_id": adapter.plan.planned_run_id,
        "case_count": 10,
        "chemistry_ready_case_ids": chemistry_records + ["APD-010"],
        "chemistry_ready_count": 10,
        "execution_plan_built": True,
        "offline_bundle_verified": True,
        "staging_verified": True,
        "evidence_scaffold": scaffold,
        "vina_docking_executed": False,
        "vina_received_receptor_or_ligand": False,
        "prospective_scores_or_poses_observed": False,
    }
    report["report_hash"] = sha256_json(report)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="configs/apodock001-protocol-freeze-v1.0.2.json")
    parser.add_argument("--bundle-root", default="inputs/apodock001/v1.0.2")
    parser.add_argument("--git-sha", default="offline-preflight")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    report = run(args)
    print(json.dumps({key: report[key] for key in (
        "status", "protocol_id", "bundle_id", "planned_run_id", "chemistry_ready_count",
        "execution_plan_built", "offline_bundle_verified", "staging_verified",
        "vina_docking_executed", "prospective_scores_or_poses_observed",
    )}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
