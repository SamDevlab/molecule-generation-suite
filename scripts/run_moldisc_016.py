from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc016 import run_moldisc_016


DEFAULT_CONFIG = Path("programs/moldisc-016-je2-source-megacampaign/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen MOLDISC-016 JE2 source-directed robustness megacampaign")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    result = run_moldisc_016(config_path=args.config, output_root=args.output, timeout=args.timeout)
    print(json.dumps({
        "program_id": result["program_id"],
        "program_protocol_hash": result["program_protocol_hash"],
        "program_scientific_hash": result["program_scientific_hash"],
        "control_replay_status": result["control_replay"]["status"],
        "docking_runs_planned": result["docking_runs_planned"],
        "docking_runs_executed": result["docking_runs_executed"],
        "docking_runs_skipped": result["docking_runs_skipped"],
        "docking_runs_nonpass": result["docking_runs_nonpass"],
        "candidate_selection_executed": False,
        "lead_selection_executed": False,
        "generation_executed": False,
        "source_measurement_transfer_allowed": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
