from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.benchmark.solubility import download_delaney, parse_delaney_csv
from research_os.benchmark.solubility_replication import DEFAULT_SEEDS, run_solubility_replication


def _seeds(value: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("seeds must be comma-separated integers") from exc
    if len(result) < 2:
        raise argparse.ArgumentTypeError("at least two seeds are required")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Replicate ONLINE-EXP-001 across multiple partition seeds")
    parser.add_argument("--csv", type=Path, help="Local Delaney/ESOL CSV; otherwise retrieve the recorded HTTPS source")
    parser.add_argument("--output", type=Path, help="Optional JSON replication report path")
    parser.add_argument("--seeds", type=_seeds, default=DEFAULT_SEEDS, help="Comma-separated seeds")
    args = parser.parse_args()

    records = parse_delaney_csv(args.csv.read_text(encoding="utf-8")) if args.csv else download_delaney()
    report = run_solubility_replication(records, seeds=args.seeds)
    if args.output:
        report.write(args.output)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
