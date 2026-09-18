from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc002 import run_moldisc_002


DEFAULT_CONFIG = Path("programs/moldisc-002-aqsoldb-coverage/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run frozen MOLDISC-002 AqSolDB structural coverage study"
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    result = run_moldisc_002(
        config_path=args.config,
        output_root=args.output,
        timeout=args.timeout,
    )
    print(
        json.dumps(
            {
                "program_id": result.program_id,
                "parent_generation_scientific_hash": result.parent_generation_scientific_hash,
                "coverage_scientific_hash": result.coverage.scientific_hash,
                "program_scientific_hash": result.program_scientific_hash,
                "source_row_count": result.coverage.source_row_count,
                "unique_structure_count": result.coverage.unique_structure_count,
                "invalid_structure_count": result.coverage.invalid_structure_count,
                "candidates": [
                    {
                        "candidate_id": item.candidate_id,
                        "nearest_similarity": item.nearest_similarity,
                        "similarity_bin": item.similarity_bin,
                        "neighbors_ge_0_4": item.neighbors_ge_0_4,
                        "neighbors_ge_0_6": item.neighbors_ge_0_6,
                        "neighbors_ge_0_8": item.neighbors_ge_0_8,
                        "top_neighbor": (
                            item.top_neighbors[0].to_dict()
                            if item.top_neighbors
                            else None
                        ),
                    }
                    for item in result.coverage.candidates
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
