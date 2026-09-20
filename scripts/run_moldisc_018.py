from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc018 import run_moldisc_018


DEFAULT_CONFIG = Path("programs/moldisc-018-reciprocal-holo-validation/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the frozen MOLDISC-018 reciprocal holo cross-docking validation megacampaign")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--source-audit-only", action="store_true")
    parser.add_argument("--no-profile-update", action="store_true")
    args = parser.parse_args()
    result = run_moldisc_018(config_path=args.config, output_root=args.output, timeout=args.timeout, source_audit_only=args.source_audit_only, update_profile=not args.no_profile_update)
    keys = ("program_id", "program_protocol_hash", "program_scientific_hash", "source_audit_hash", "docking_runs_planned", "docking_runs_executed", "docking_runs_skipped", "docking_runs_nonpass", "generation_executed", "generated_candidate_docking_executed", "candidate_selection_executed", "lead_selection_executed", "profile_update")
    print(json.dumps({key: result.get(key) for key in keys}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
