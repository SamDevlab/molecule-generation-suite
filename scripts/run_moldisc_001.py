from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_os.molecular_discovery import FrozenESOLSolubilityPredictor, run_moldisc_001


DEFAULT_CONFIG = Path("programs/moldisc-001-id5/program.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen MOLDISC-001 (PDB 1T40 / ID5)")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--esol-csv",
        help="local exact Delaney/ESOL CSV; otherwise the recorded public source is downloaded and identity checked",
    )
    args = parser.parse_args()

    predictor = (
        FrozenESOLSolubilityPredictor.from_esol_csv(args.esol_csv)
        if args.esol_csv
        else FrozenESOLSolubilityPredictor.from_public_source()
    )
    result = run_moldisc_001(
        config_path=args.config,
        output_root=args.output,
        predictor=predictor,
    )
    print(
        json.dumps(
            {
                "program_id": result.program_id,
                "candidate_count": result.candidate_count,
                "generated_count": result.generation.candidate_count,
                "generation_scientific_hash": result.generation.scientific_hash,
                "workflow_scientific_summary_hash": result.discovery_report.scientific_summary_hash,
                "program_scientific_hash": result.program_scientific_hash,
                "triage": [
                    {
                        "review_order": item.review_order,
                        "candidate_id": item.candidate_id,
                        "priority_group": item.priority_group,
                        "solubility_status": item.solubility_status,
                        "predicted_log_s_mol_l": (item.solubility or {}).get("predicted_log_s_mol_l"),
                        "max_training_tanimoto": (item.solubility or {}).get("max_training_tanimoto"),
                    }
                    for item in result.discovery_report.candidates
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
