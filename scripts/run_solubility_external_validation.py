from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.benchmark.reproducibility import reproducibility_metadata
from research_os.benchmark.solubility_external import run_online_exp_002_from_public_sources


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ONLINE-EXP-002 decontaminated AqSolDB external validation")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = run_online_exp_002_from_public_sources()
    payload = report.to_dict()
    payload["reproducibility"] = reproducibility_metadata(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
