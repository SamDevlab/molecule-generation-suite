from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc008 import run_moldisc_008


DEFAULT_CONFIG = Path("programs/moldisc-008-je2-evidence-profile/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen MOLDISC-008 JE2 evidence profile")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = run_moldisc_008(config_path=args.config, output_root=args.output)
    print(
        json.dumps(
            {
                "program_id": result.program_id,
                "rcsb_identity": result.rcsb_identity.scientific_dict(),
                "profile": result.profile.to_dict(),
                "workflow_scientific_summary_hash": result.workflow_scientific_summary_hash,
                "aqsoldb_coverage_scientific_hash": result.coverage.scientific_hash,
                "program_scientific_hash": result.program_scientific_hash,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
