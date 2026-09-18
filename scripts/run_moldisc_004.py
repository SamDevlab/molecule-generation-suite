from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc004 import run_moldisc_004


DEFAULT_CONFIG = Path("programs/moldisc-004-nct-measured-anchor/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run frozen MOLDISC-004 NCT measured-anchor calibration"
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    result = run_moldisc_004(
        config_path=args.config,
        output_root=args.output,
        timeout=args.timeout,
    )
    print(
        json.dumps(
            {
                "program_id": result.program_id,
                "anchor": result.anchor.to_dict(),
                "calibration": result.calibration.to_dict(),
                "workflow_scientific_summary_hash": result.workflow_scientific_summary_hash,
                "program_scientific_hash": result.program_scientific_hash,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
