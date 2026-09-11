from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from research_os.docking import crossdock001
from research_os.docking.crossdock001_runner import run_frozen_crossdock001


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute frozen CROSSDOCK-001 rigid holo-holo benchmark")
    parser.add_argument("--workdir", default=".crossdock001-run")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    report = run_frozen_crossdock001(args.workdir)
    output = Path(args.output) if args.output else Path(args.workdir) / "crossdock001-result-v1.0.json"
    produced = Path(args.workdir) / "crossdock001-result-v1.0.json"
    if output.resolve() != produced.resolve():
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(produced, output)

    compact = {
        "benchmark_id": report["benchmark_id"],
        "protocol_id": report["protocol_id"],
        "summary": report["summary"],
        "scientific_result_hash": report["scientific_result_hash"],
        "execution_hash": report["execution_hash"],
        "cases": [
            {
                "case_id": record["result"]["case_id"],
                "source": record["case"]["source"]["pdb_id"],
                "target": record["case"]["target"]["pdb_id"],
                "status": record["result"]["status"],
                "pose_1_rmsd_angstrom": record["result"]["pose_1_rmsd_angstrom"],
                "minimum_rmsd_angstrom": record["result"]["minimum_rmsd_angstrom"],
                "first_near_native_rank": record["result"]["first_near_native_rank"],
                "pose_count": record["result"]["pose_count"],
                "vina_pose_1_score_kcal_mol": record["result"]["vina_pose_1_score_kcal_mol"],
            }
            for record in report["records"]
        ],
    }
    print(json.dumps(compact, indent=2, sort_keys=True))

    if len(report["records"]) != crossdock001.DIRECTED_CASE_COUNT:
        print("CROSSDOCK-001 execution did not retain the frozen 10-case denominator")
        return 1
    technical_failures = [
        record["result"]["case_id"]
        for record in report["records"]
        if record["result"]["status"] != "PASS"
    ]
    if technical_failures:
        print(f"CROSSDOCK-001 technical failures: {technical_failures}")
        return 1

    # Scientific failures (rank-1 RMSD > 2 Å) are intentionally NOT CI failures.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
