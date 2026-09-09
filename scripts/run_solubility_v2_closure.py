from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.benchmark.solubility import download_delaney, parse_delaney_csv
from research_os.benchmark.solubility_v2_closure import (
    DEFAULT_SEEDS,
    run_v2_dataset_sensitivity,
    run_v2_robustness,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Close ONLINE-EXP-001 v2 with robustness and dataset sensitivity checks")
    parser.add_argument("--csv", type=Path, help="Optional local Delaney CSV instead of network retrieval")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="*", default=list(DEFAULT_SEEDS))
    parser.add_argument("--sensitivity-seed", type=int, default=42)
    args = parser.parse_args()

    records = download_delaney() if args.csv is None else parse_delaney_csv(args.csv.read_text(encoding="utf-8"))
    payload = {
        "robustness": run_v2_robustness(records, seeds=tuple(args.seeds)),
        "dataset_sensitivity": run_v2_dataset_sensitivity(records, seed=args.sensitivity_seed),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
