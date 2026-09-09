from __future__ import annotations

import pytest

from research_os.benchmark.solubility import (
    DESCRIPTOR_NAMES,
    SolubilityBenchmarkError,
    SolubilityRecord,
    balanced_scaffold_split,
    dataset_hash,
    descriptor_vector,
    parse_delaney_csv,
    run_solubility_benchmark,
    scaffold_overlap_count,
)


def test_parse_delaney_csv_accepts_deepchem_headers_and_hashes_deterministically():
    text = """Compound ID,measured log solubility in mols per litre,smiles\nethanol,-0.3,CCO\nbenzene,-2.1,c1ccccc1\n"""
    records = parse_delaney_csv(text)
    assert len(records) == 2
    assert records[0].measured_log_s_mol_l == -0.3
    assert dataset_hash(records) == dataset_hash(tuple(records))


def test_parse_delaney_csv_fails_closed_on_missing_target():
    with pytest.raises(SolubilityBenchmarkError, match="missing SMILES or measured logS"):
        parse_delaney_csv("Compound ID,smiles\nethanol,CCO\n")


def test_descriptor_vector_is_finite_and_schema_aligned():
    vector = descriptor_vector("CCO")
    assert len(vector) == len(DESCRIPTOR_NAMES)
    assert all(isinstance(value, float) for value in vector)


def test_descriptor_vector_rejects_invalid_smiles():
    with pytest.raises(SolubilityBenchmarkError, match="invalid SMILES"):
        descriptor_vector("this-is-not-smiles")


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


def test_balanced_scaffold_split_is_disjoint_and_keeps_large_group_out_of_test_when_possible():
    split = balanced_scaffold_split(_records(), seed=7, validation_size=0.1, test_size=0.1)
    assert scaffold_overlap_count(split) == 0
    assert len(split.train) > len(split.test)
    assert split.metadata["allocation"] == "descending_group_size_greedy"


def test_online_exp_001_runs_fixed_models_and_keeps_scaffolds_disjoint():
    pytest.importorskip("sklearn")
    report = run_solubility_benchmark(_records(), seed=7)
    assert report.experiment_id == "ONLINE-EXP-001"
    assert report.record_count == len(_records())
    assert report.report_hash
    assert {split.strategy for split in report.splits} == {"random", "scaffold"}
    scaffold = next(split for split in report.splits if split.strategy == "scaffold")
    assert scaffold.scaffold_overlap_count == 0
    assert {model.model for model in scaffold.models} == {"mean_baseline", "ridge", "random_forest"}
    for split in report.splits:
        for model in split.models:
            assert model.test_count > 0
            assert model.test_metrics.rmse >= 0
            assert model.hyperparameters
    assert set(report.generalization_gap_rmse) == {"mean_baseline", "ridge", "random_forest"}


def test_report_is_deterministic_for_same_seed_and_records():
    pytest.importorskip("sklearn")
    first = run_solubility_benchmark(_records(), seed=11)
    second = run_solubility_benchmark(_records(), seed=11)
    assert first.to_dict() == second.to_dict()
