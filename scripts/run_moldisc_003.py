from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery.moldisc003 import run_moldisc_003


DEFAULT_CONFIG = Path("programs/moldisc-003-redock-seed-coverage/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run frozen MOLDISC-003 REDOCK-003 seed coverage scan"
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    result = run_moldisc_003(
        config_path=args.config,
        output_root=args.output,
        timeout=args.timeout,
    )
    print(
        json.dumps(
            {
                "program_id": result.program_id,
                "rcsb_identity_hash": result.rcsb_identity_hash,
                "coverage_scientific_hash": result.coverage.scientific_hash,
                "program_scientific_hash": result.program_scientific_hash,
                "selection": result.selection.to_dict(),
                "candidates": [
                    {
                        "case_id": item.candidate_id,
                        "nearest_similarity": item.nearest_similarity,
                        "similarity_bin": item.similarity_bin,
                        "neighbors_ge_0_4": item.neighbors_ge_0_4,
                        "top_neighbor": item.top_neighbors[0].to_dict() if item.top_neighbors else None,
                    }
                    for item in sorted(
                        result.coverage.candidates,
                        key=lambda row: (-row.nearest_similarity, row.candidate_id),
                    )
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
