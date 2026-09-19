from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc009 import run_moldisc_009


DEFAULT_CONFIG = Path("programs/moldisc-009-je2-demethyl-series/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen MOLDISC-009 JE2 demethyl series")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = run_moldisc_009(config_path=args.config, output_root=args.output)
    print(
        json.dumps(
            {
                "program_id": result.program_id,
                "generation_scientific_hash": result.generation_scientific_hash,
                "workflow_scientific_summary_hash": result.workflow_scientific_summary_hash,
                "coverage_scientific_hash": result.coverage_scientific_hash,
                "selection": result.selection.to_dict(),
                "profiles": [item.to_dict() for item in result.profiles],
                "program_scientific_hash": result.program_scientific_hash,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
