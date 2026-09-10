from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.docking.redocking_v12 import FROZEN_REDOCKING_CASES, run_frozen_redocking_benchmark
from research_os.docking.redocking_v12_identity import execution_hash, scientific_result_hash


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute frozen REDOCK-001 v1.2")
    parser.add_argument("--workdir", default=".redocking-work-v12")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    report = run_frozen_redocking_benchmark(args.workdir)
    # The scientific identity excludes runtime timing, local paths and host-only
    # diagnostics. The raw implementation hash is retained for audit only.
    report["raw_runtime_coupled_hash"] = report.get("scientific_result_hash")
    stable_scientific_hash = scientific_result_hash(report)
    report["scientific_result_hash"] = stable_scientific_hash
    report["execution_hash"] = execution_hash(report, stable_scientific_hash)

    output = Path(args.output) if args.output else Path(args.workdir) / "redocking-result-v1.2.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    summary = report["summary"]
    compact = {
        "protocol_id": report["protocol_id"],
        "scientific_result_hash": report["scientific_result_hash"],
        "execution_hash": report["execution_hash"],
        "total_cases": summary["total_cases"],
        "passing_rmsd_cases": summary["passing_rmsd_cases"],
        "status_counts": summary["status_counts"],
        "pose_1_rmsd_angstrom": summary["pose_1_rmsd_angstrom"],
        "pose_1_rmsd_le_2_angstrom": summary["pose_1_rmsd_le_2_angstrom"],
        "cases": [record["result"] for record in report["records"]],
        "environment": report["environment"],
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False, sort_keys=True))

    if len(report["records"]) != len(FROZEN_REDOCKING_CASES):
        raise SystemExit("frozen case count was not preserved")
    executed = sum(bool(record.get("provenance", {}).get("docking")) for record in report["records"])
    if executed == 0:
        raise SystemExit("no frozen case reached real Vina execution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
