from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.docking.astex20 import FROZEN_PROSPECTIVE_CASES, PROTOCOL_ID
from research_os.docking.astex20_runner import run_frozen_astex20_prospective_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute frozen REDOCK-003 Astex-20 15-case prospective extension v1.0"
    )
    parser.add_argument("--workdir", default=".astex20-redocking-work-v1")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    report = run_frozen_astex20_prospective_benchmark(args.workdir)
    output = Path(args.output) if args.output else Path(args.workdir) / "redocking-astex20-result-v1.0.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    summary = report["summary"]
    compact = {
        "benchmark_id": report["benchmark_id"],
        "protocol_id": report["protocol_id"],
        "evaluator_protocol_id": report["evaluator_protocol_id"],
        "scientific_result_hash": report["scientific_result_hash"],
        "execution_hash": report["execution_hash"],
        "preflight": report["preflight"],
        "primary_prospective_summary": summary,
        "descriptive_astex20": report["descriptive_astex20"],
        "cases": [record["result"] for record in report["records"]],
        "environment": report["environment"],
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False, sort_keys=True))

    if report["protocol_id"] != PROTOCOL_ID:
        raise SystemExit("Astex-20 protocol identity changed")
    if len(report["records"]) != len(FROZEN_PROSPECTIVE_CASES) != 15:
        raise SystemExit("frozen Astex-20 prospective case count was not preserved")
    executed = sum(bool(record.get("provenance", {}).get("docking")) for record in report["records"])
    if executed == 0:
        raise SystemExit("no frozen Astex-20 case reached real Vina execution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
