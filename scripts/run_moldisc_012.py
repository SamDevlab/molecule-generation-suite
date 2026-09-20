from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc012 import run_moldisc_012


DEFAULT_CONFIG = Path("programs/moldisc-012-step2-demethyl01-crossdock/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen MOLDISC-012 STEP2-DEMETHYL-01 / 1KZK cross-docking")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run_moldisc_012(config_path=args.config, output_root=args.output)
    print(json.dumps({
        "program_id": result.program_id,
        "candidate_variant_id": result.candidate_variant_id,
        "candidate_id": result.candidate_id,
        "candidate_inchikey": result.candidate_inchikey,
        "technical_status": result.technical_status,
        "pose_count": result.pose_count,
        "pose_scores_kcal_mol": list(result.pose_scores_kcal_mol),
        "grid_hash": result.grid.get("grid_hash"),
        "native_reference_structure_hash": result.native_reference_structure_hash,
        "vina_output_scientific_hash": result.vina_output_scientific_hash,
        "capability": result.capability,
        "program_scientific_hash": result.program_scientific_hash,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
