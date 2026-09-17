from __future__ import annotations

import argparse
import csv
from pathlib import Path

from research_os.molecular_discovery import (
    FrozenESOLSolubilityPredictor,
    MolecularDiscoveryWorkflow,
)


def _load_candidates(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("candidate CSV is missing a header")
        if "smiles" not in reader.fieldnames and "SMILES" not in reader.fieldnames:
            raise ValueError("candidate CSV requires a smiles or SMILES column")
        return [dict(row) for row in reader if any(str(value or "").strip() for value in row.values())]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Molecular Discovery Program v0.1")
    parser.add_argument("candidates", help="CSV with id/name/smiles columns")
    parser.add_argument("--output", required=True, help="new output directory")
    parser.add_argument(
        "--esol-csv",
        help="local Delaney/ESOL CSV; when omitted the recorded public source is downloaded and identity-checked",
    )
    args = parser.parse_args()

    predictor = (
        FrozenESOLSolubilityPredictor.from_esol_csv(args.esol_csv)
        if args.esol_csv
        else FrozenESOLSolubilityPredictor.from_public_source()
    )
    workflow = MolecularDiscoveryWorkflow(solubility_predictor=predictor)
    report = workflow.run_to_directory(_load_candidates(args.candidates), args.output)
    print(report.scientific_summary_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
