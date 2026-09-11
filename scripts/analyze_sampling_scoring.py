from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.docking.sampling_scoring_diagnostic import (
    analyze_sampling_scoring,
    load_sealed_input,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze sampling-versus-ranking failure modes from the sealed RANK-002 snapshot."
    )
    parser.add_argument("input", type=Path, help="Sealed RANK-002 source snapshot")
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()

    payload = load_sealed_input(args.input)
    result = analyze_sampling_scoring(payload)
    text = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
