from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc015 import run_moldisc_015


DEFAULT_CONFIG = Path("programs/moldisc-015-c2545-source-resolution/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen MOLDISC-015 C-2545 source-resolution program")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--aqsoldb-csv", required=True)
    parser.add_argument("--dataset-c-readme", required=True)
    parser.add_argument("--supporting-information-manifest")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run_moldisc_015(
        config_path=args.config,
        aqsoldb_csv_path=args.aqsoldb_csv,
        dataset_c_readme_path=args.dataset_c_readme,
        supporting_information_manifest_path=args.supporting_information_manifest,
        output_root=args.output,
    )
    print(json.dumps({
        "program_id": "MOLDISC-015",
        "resolution_status": result.identity_resolution.status,
        "source_trace_hash": result.source_trace_hash,
        "identity_resolution_hash": result.identity_resolution_hash,
        "program_scientific_hash": result.program_scientific_hash,
        "measurement_transfer_allowed": result.identity_resolution.measurement_transfer["measurement_transfer_allowed"],
        "generation_executed": False,
        "docking_executed": False,
        "esol_executed": False,
        "candidate_selection_executed": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
