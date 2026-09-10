from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.docking.redocking import FROZEN_REDOCKING_CASES, run_frozen_redocking_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute frozen REDOCK-001 v1.1")
    parser.add_argument("--workdir", default=".redocking-work")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    report = run_frozen_redocking_benchmark(args.workdir)
    output = Path(args.output) if args.output else Path(args.workdir) / "redocking-result.json"
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
