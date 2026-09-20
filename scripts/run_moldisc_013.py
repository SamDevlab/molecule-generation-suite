from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc013 import run_moldisc_013


DEFAULT_CONFIG = Path("programs/moldisc-013-common-core-pose-diagnostic/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen MOLDISC-013 common-core receptor-frame pose geometry diagnostic")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run_moldisc_013(config_path=args.config, output_root=args.output)
    print(json.dumps({
        "program_id": result.program_id,
        "parent_moldisc010_replay_hash": result.parent_moldisc010_replay_hash,
        "child_moldisc012_replay_hash": result.child_moldisc012_replay_hash,
        "matrix_shape": list(result.matrix_shape),
        "rank1_pair_common_core_rmsd_angstrom": result.rank1_pair_common_core_rmsd_angstrom,
        "minimum_all_pairs_common_core_rmsd_angstrom": result.minimum_all_pairs_common_core_rmsd_angstrom,
        "minimum_all_pairs_parent_rank": result.minimum_all_pairs_parent_rank,
        "minimum_all_pairs_child_rank": result.minimum_all_pairs_child_rank,
        "parent_rank1_to_child_ensemble_min_rmsd_angstrom": result.parent_rank1_to_child_ensemble_min_rmsd_angstrom,
        "parent_rank1_to_child_ensemble_child_rank": result.parent_rank1_to_child_ensemble_child_rank,
        "child_rank1_to_parent_ensemble_min_rmsd_angstrom": result.child_rank1_to_parent_ensemble_min_rmsd_angstrom,
        "child_rank1_to_parent_ensemble_parent_rank": result.child_rank1_to_parent_ensemble_parent_rank,
        "common_core_mapping_hash": result.common_core_mapping_hash,
        "matrix_hash": result.matrix_hash,
        "analysis_a_program_hash": result.analysis_a_program_hash,
        "analysis_b_program_hash": result.analysis_b_program_hash,
        "program_scientific_hash": result.program_scientific_hash,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
