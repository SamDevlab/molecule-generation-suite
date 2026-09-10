from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.docking.redocking_holdout import FROZEN_HOLDOUT_CASES, PROTOCOL_ID
from research_os.docking.redocking_holdout_runner import run_frozen_holdout_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute frozen REDOCK-002 Astex holdout v1.0")
    parser.add_argument("--workdir", default=".redocking-holdout-work-v1")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    report = run_frozen_holdout_benchmark(args.workdir)
    output = Path(args.output) if args.output else Path(args.workdir) / "redocking-holdout-result-v1.0.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    summary = report["summary"]
    compact = {
        "protocol_id": report["protocol_id"],
        "evaluator_protocol_id": report["evaluator_protocol_id"],
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

    if report["protocol_id"] != PROTOCOL_ID:
        raise SystemExit("holdout protocol identity changed")
    if len(report["records"]) != len(FROZEN_HOLDOUT_CASES):
        raise SystemExit("frozen holdout case count was not preserved")
    executed = sum(bool(record.get("provenance", {}).get("docking")) for record in report["records"])
    if executed == 0:
        raise SystemExit("no frozen holdout case reached real Vina execution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
