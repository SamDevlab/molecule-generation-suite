from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.docking.ranking_diagnostic import analyze_ranking, load_sealed_input


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze sealed REDOCK-003 Astex-20 pose ranking.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = load_sealed_input(args.input)
    report = analyze_ranking(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
