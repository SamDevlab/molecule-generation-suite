from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc006 import run_moldisc_006


DEFAULT_CONFIG = Path("programs/moldisc-006-nh-crossdock/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen MOLDISC-006 N-H cross-docking program")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = run_moldisc_006(config_path=args.config, output_root=args.output)
    print(
        json.dumps(
            {
                "program_id": result.program_id,
                "technical_status": result.technical_status,
                "pose_count": result.pose_count,
                "vina_pose_1_score_kcal_mol": result.vina_pose_1_score_kcal_mol,
                "best_affinity_kcal_mol": result.best_affinity_kcal_mol,
                "candidate_id": result.candidate_id,
                "candidate_inchikey": result.candidate_inchikey,
                "grid_hash": result.grid.get("grid_hash"),
                "capability": result.capability,
                "program_scientific_hash": result.program_scientific_hash,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
