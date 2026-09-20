from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc014 import run_moldisc_014


DEFAULT_CONFIG = Path("programs/moldisc-014-aqsoldb-source-interpolation/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen MOLDISC-014 source-directed AqSolDB interpolation panel")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run_moldisc_014(config_path=args.config, output_root=args.output)
    print(json.dumps({
        "program_id": result.program_id,
        "generation_scientific_hash": result.generation_scientific_hash,
        "source_audit_scientific_hash": result.source_audit_scientific_hash,
        "workflow_scientific_summary_hash": result.workflow_scientific_summary_hash,
        "coverage_scientific_hash": result.coverage_scientific_hash,
        "program_scientific_hash": result.program_scientific_hash,
        "panel_variant_ids": [item.variant_id for item in result.panel],
        "candidate_selection_executed": False,
        "docking_executed": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
