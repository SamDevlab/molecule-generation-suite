from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc017 import run_moldisc_017


DEFAULT_CONFIG = Path("programs/moldisc-017-hiv-protease-receptor-state/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the frozen MOLDISC-017 HIV-1 protease receptor-state megacampaign")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--moldisc016-artifact", default=None)
    parser.add_argument("--source-audit-only", action="store_true")
    args = parser.parse_args()
    result = run_moldisc_017(config_path=args.config, output_root=args.output, timeout=args.timeout, moldisc016_artifact=args.moldisc016_artifact, source_audit_only=args.source_audit_only)
    print(json.dumps({key: result.get(key) for key in ("program_id", "program_protocol_hash", "program_scientific_hash", "source_audit_hash", "docking_runs_planned", "docking_runs_executed", "docking_runs_skipped", "docking_runs_nonpass", "generation_executed", "candidate_selection_executed", "lead_selection_executed", "source_measurement_transfer_allowed")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
