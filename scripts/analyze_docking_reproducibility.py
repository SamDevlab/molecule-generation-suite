from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.docking.reproducibility import analyze_replicates, load_reports


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare repeated docking reports and classify endpoint reproducibility."
    )
    parser.add_argument("reports", nargs="+", help="Docking result JSON files in replicate order")
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    parser.add_argument(
        "--threshold",
        type=float,
        default=2.0,
        help="RMSD success threshold in angstrom (default: 2.0)",
    )
    args = parser.parse_args()

    reports = load_reports(args.reports)
    diagnostic = analyze_replicates(reports, success_threshold_angstrom=args.threshold)
    text = json.dumps(diagnostic, indent=2, ensure_ascii=False, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
