from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc007 import run_moldisc_007


DEFAULT_CONFIG = Path("programs/moldisc-007-operational-fallback/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen MOLDISC-007 operational fallback selection")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = run_moldisc_007(config_path=args.config, output_root=args.output)
    print(
        json.dumps(
            {
                "program_id": result.program_id,
                "selection": result.selection.to_dict(),
                "program_scientific_hash": result.program_scientific_hash,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
