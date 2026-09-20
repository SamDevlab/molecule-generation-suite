from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.experimental_handoff import generate_handoff


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "experimental_packages" / "biolab-physical-loop-0"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the deterministic BIOEXP-001 laboratory handoff")
    parser.add_argument("--experiment", default="BIOEXP-001-SOLUBILITY-2X2")
    parser.add_argument("--source-package", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    if args.experiment != "BIOEXP-001-SOLUBILITY-2X2":
        parser.error("only the frozen BIOEXP-001-SOLUBILITY-2X2 handoff is supported")
    manifest = generate_handoff(args.source_package, args.output, ROOT)
    print(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
