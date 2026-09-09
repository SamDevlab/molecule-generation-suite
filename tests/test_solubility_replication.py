from __future__ import annotations

import pytest

from research_os.benchmark.solubility import SolubilityRecord
from research_os.benchmark.solubility_replication import run_solubility_replication, summarize


def _records() -> tuple[SolubilityRecord, ...]:
    smiles = (
        "CCO", "CCCO", "CCCCO", "CCN", "CCCN", "CCCCN",
        "c1ccccc1", "Cc1ccccc1", "Oc1ccccc1", "Nc1ccccc1",
        "c1ccncc1", "Cc1ccncc1", "c1ccoc1", "c1ccsc1",
        "C1CCCCC1", "OC1CCCCC1", "N1CCCCC1", "C1CCNCC1",
        "c1ccc2ccccc2c1", "Oc1ccc2ccccc2c1", "c1ccc2[nH]ccc2c1",
        "O=C1CCCCC1", "O=C1NC=CC=C1", "CC(=O)Oc1ccccc1",
        "CCOC(=O)c1ccccc1", "CC(C)O", "CC(C)CO", "CC(C)(C)O",
        "O=C(O)c1ccccc1", "N#Cc1ccccc1", "COc1ccccc1", "Clc1ccccc1",
        "Fc1ccccc1", "Brc1ccccc1", "CC1=CC=CC=C1", "CC1=CC=CN=C1",
    )
    return tuple(
        SolubilityRecord(f"mol-{index:02d}", value, -0.15 * len(value) + (index % 5) * 0.08)
        for index, value in enumerate(smiles)
    )


def test_metric_summary_uses_sample_stdev_and_none_for_singleton():
    assert summarize([2.0]).stdev is None
    summary = summarize([1.0, 2.0, 3.0])
    assert summary.mean == 2.0
    assert summary.stdev == 1.0
    assert summary.minimum == 1.0
    assert summary.maximum == 3.0


def test_replication_requires_unique_multiple_seeds():
    with pytest.raises(ValueError, match="at least two"):
        run_solubility_replication(_records(), seeds=(42,))
    with pytest.raises(ValueError, match="unique"):
        run_solubility_replication(_records(), seeds=(42, 42))


def test_replication_is_deterministic_and_records_dispersion():
    pytest.importorskip("sklearn")
    first = run_solubility_replication(_records(), seeds=(7, 42))
    second = run_solubility_replication(_records(), seeds=(7, 42))
    assert first.to_dict() == second.to_dict()
    assert first.seeds == (7, 42)
    assert len(first.run_report_hashes) == 2
    assert {item.model for item in first.models} == {"mean_baseline", "ridge", "random_forest"}
    for item in first.models:
        assert item.random_rmse.n == 2
        assert item.scaffold_rmse.n == 2
        assert item.rmse_generalization_gap.stdev is not None
