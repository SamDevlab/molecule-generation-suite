from __future__ import annotations

import math

import pytest

from research_os.benchmark.solubility import SolubilityRecord
from research_os.benchmark.solubility_v2 import (
    AD_TRAIN_QUANTILE,
    ACYCLIC_CLUSTER_SIMILARITY,
    audit_chemistry,
    delaney_original_prediction,
    hybrid_group_labels,
    hybrid_structural_split,
    run_solubility_benchmark_v2,
    structural_overlap_count,
)


def _records() -> tuple[SolubilityRecord, ...]:
    smiles = (
        "CCO", "CCCO", "CCCCO", "CCN", "CCCN", "CCCCN",
        "CC(C)O", "CC(C)CO", "CC(C)(C)O", "CCOC", "CCCOC", "CCCCOC",
        "c1ccccc1", "Cc1ccccc1", "Oc1ccccc1", "Nc1ccccc1",
        "c1ccncc1", "Cc1ccncc1", "c1ccoc1", "c1ccsc1",
        "C1CCCCC1", "OC1CCCCC1", "N1CCCCC1", "C1CCNCC1",
        "c1ccc2ccccc2c1", "Oc1ccc2ccccc2c1", "c1ccc2[nH]ccc2c1",
        "O=C1CCCCC1", "O=C1NC=CC=C1", "CC(=O)Oc1ccccc1",
        "CCOC(=O)c1ccccc1", "O=C(O)c1ccccc1", "N#Cc1ccccc1",
        "COc1ccccc1", "Clc1ccccc1", "Fc1ccccc1", "Brc1ccccc1",
        "CC1=CC=CC=C1", "CC1=CC=CN=C1",
    )
    return tuple(
        SolubilityRecord(f"mol-{index:02d}", smiles_value, -0.15 * len(smiles_value) + (index % 5) * 0.08)
        for index, smiles_value in enumerate(smiles)
    )


def test_chemical_audit_reports_duplicates_conflicts_fragments_and_charges_without_silent_removal():
    records = (
        SolubilityRecord("a", "CCO", -0.3),
        SolubilityRecord("b", "OCC", -0.7),
        SolubilityRecord("c", "CC.[Na+]", -1.0),
    )
    audit = audit_chemistry(records)
    assert audit.raw_records == 3
    assert audit.valid_records == 3
    assert audit.unique_structures == 2
    assert audit.duplicate_structure_groups == 1
    assert audit.conflicting_target_groups == 1
    assert audit.multi_fragment_records == 1
    assert audit.charged_records == 1
    assert audit.audit_hash


def test_hybrid_grouping_does_not_collapse_every_acyclic_molecule_into_one_scaffold():
    records = tuple(
        SolubilityRecord(str(index), smiles, -1.0)
        for index, smiles in enumerate(("CCO", "CCCCCCCC", "N#N", "CC(=O)O", "c1ccccc1"))
    )
    labels = hybrid_group_labels(records)
    acyclic_labels = {label for label in labels if label.startswith("ACYCLIC:")}
    assert len(acyclic_labels) > 1
    assert any(label.startswith("RING:") for label in labels)
    assert ACYCLIC_CLUSTER_SIMILARITY == 0.50


def test_hybrid_split_preserves_structural_groups_and_reasonable_target_sizes():
    split = hybrid_structural_split(_records(), seed=7)
    assert structural_overlap_count(split) == 0
    assert len(split.train) > len(split.validation)
    assert len(split.train) > len(split.test)
    assert abs(len(split.validation) - len(split.test)) <= 2
    assert split.metadata["grouping"].startswith("murcko_for_ring_systems")


def test_original_delaney_formula_is_fixed_and_deterministic():
    first = delaney_original_prediction("CCO")
    second = delaney_original_prediction("CCO")
    assert math.isfinite(first)
    assert first == second


def test_v2_runs_frozen_model_and_representation_matrix():
    pytest.importorskip("sklearn")
    report = run_solubility_benchmark_v2(_records(), seed=7)
    assert report.experiment_id == "ONLINE-EXP-001-V2"
    assert report.protocol_version.endswith(".v2")
    assert report.chemical_audit.invalid_records == 0
    assert {split.strategy for split in report.splits} == {"random", "hybrid_structural"}
    structural = next(split for split in report.splits if split.strategy == "hybrid_structural")
    assert structural.structural_overlap_count == 0
    assert {model.model for model in structural.models} == {
        "mean_baseline",
        "delaney_original",
        "ridge",
        "random_forest_descriptors",
        "random_forest_morgan",
        "random_forest_combined",
    }
    assert structural.target_distribution["test"].stdev is not None


def test_applicability_threshold_is_training_derived_and_partitions_test_records():
    pytest.importorskip("sklearn")
    report = run_solubility_benchmark_v2(_records(), seed=11)
    domain = report.applicability_domain
    structural = next(split for split in report.splits if split.strategy == "hybrid_structural")
    assert AD_TRAIN_QUANTILE == 0.05
    assert 0.0 <= domain.threshold <= 1.0
    assert "training leave-one-out" in domain.threshold_source
    for summary in domain.model_summaries:
        assert summary.in_domain_count + summary.out_of_domain_count == structural.test_count
    assert sum(bucket.n for bucket in domain.combined_rf_similarity_bins) == structural.test_count


def test_descriptor_ablation_uses_validation_only_and_preserves_all_features_in_tested_model():
    pytest.importorskip("sklearn")
    report = run_solubility_benchmark_v2(_records(), seed=13)
    assert "all_descriptors" in report.validation_ablation
    assert "without_mol_log_p" in report.validation_ablation
    assert len(report.validation_ablation) == 9
    assert all(value >= 0 for value in report.validation_ablation.values())


def test_v2_report_is_deterministic_for_same_seed():
    pytest.importorskip("sklearn")
    first = run_solubility_benchmark_v2(_records(), seed=17)
    second = run_solubility_benchmark_v2(_records(), seed=17)
    assert first.to_dict() == second.to_dict()
