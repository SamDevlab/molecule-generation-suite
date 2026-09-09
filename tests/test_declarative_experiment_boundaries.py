from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from research_os.experiments import ExperimentEngine, ExperimentExecutionError


def _base_protocol(dataset_path: str) -> dict:
    return {
        "protocol": "research-os.declarative-experiment.v1",
        "experiment": {"id": "BOUNDARY-REGRESSION-001", "task": "regression", "seed": 42},
        "dataset": {
            "adapter": "csv",
            "path": dataset_path,
            "target": "fuel_id",
            "features": ["smiles"],
        },
        "split": {"strategy": "random", "train_fraction": 0.8},
        "models": [{"id": "ols", "adapter": "linear_regression"}],
        "metrics": ["mae", "rmse", "r2"],
        "evidence": {
            "require_dataset_hash": True,
            "require_protocol_hash": True,
            "fail_closed": True,
        },
    }


def test_existing_textual_golden_dataset_is_rejected_not_coerced(tmp_path: Path) -> None:
    protocol_path = tmp_path / "protocol.yaml"
    protocol_path.write_text(
        yaml.safe_dump(_base_protocol("examples/golden_workflow/data/golden_fuels.csv"), sort_keys=False),
        encoding="utf-8",
    )
    with pytest.raises(ExperimentExecutionError, match="not numeric"):
        ExperimentEngine().run(protocol_path, tmp_path / "runs")


def test_declarative_engine_source_contains_no_scientific_domain_coupling() -> None:
    package = Path("src/research_os/experiments")
    forbidden = ("solubility", "smiles", "rdkit", "cantera", "aqsoldb")
    sources = "\n".join(path.read_text(encoding="utf-8").lower() for path in sorted(package.glob("*.py")))
    for identifier in forbidden:
        assert identifier not in sources, f"declarative core unexpectedly contains domain identifier: {identifier}"
