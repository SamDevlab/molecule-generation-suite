from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.benchmark.solubility import download_delaney, parse_delaney_csv
from research_os.benchmark.solubility_v2 import run_solubility_benchmark_v2


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ONLINE-EXP-001 v2")
    parser.add_argument("--csv", type=Path, help="Optional local Delaney CSV instead of network retrieval")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.csv is None:
        records = download_delaney()
    else:
        records = parse_delaney_csv(args.csv.read_text(encoding="utf-8"))

    report = run_solubility_benchmark_v2(records, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
