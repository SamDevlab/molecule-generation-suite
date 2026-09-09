from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.benchmark.reproducibility import reproducibility_metadata
from research_os.benchmark.solubility import download_delaney, parse_delaney_csv, run_solubility_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Research OS ONLINE-EXP-001 solubility benchmark")
    parser.add_argument("--csv", type=Path, help="Local Delaney/ESOL CSV. If omitted, use the recorded HTTPS source.")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.csv:
        records = parse_delaney_csv(args.csv.read_text(encoding="utf-8"))
    else:
        records = download_delaney()
    report = run_solubility_benchmark(records, seed=args.seed)
    payload = report.to_dict()
    payload["reproducibility"] = reproducibility_metadata(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
