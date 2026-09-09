from __future__ import annotations

import pytest

from research_os.benchmark.solubility import SolubilityRecord
from research_os.benchmark.solubility_v2_closure import (
    run_frozen_v2_seed,
    run_v2_dataset_sensitivity,
    run_v2_robustness,
    unique_nonconflicting_view,
)


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
        SolubilityRecord(f"mol-{index:02d}", value, -0.12 * len(value) + (index % 5) * 0.07)
        for index, value in enumerate(smiles)
    )


def test_unique_nonconflicting_view_excludes_conflicts_without_averaging_and_collapses_same_target_duplicates():
    records = (
        SolubilityRecord("a1", "CCO", -0.3),
        SolubilityRecord("a2", "OCC", -0.3),
        SolubilityRecord("b1", "CCN", -0.5),
        SolubilityRecord("b2", "NCC", -0.8),
        SolubilityRecord("c1", "c1ccccc1", -2.0),
    )
    view = unique_nonconflicting_view(records)
    assert view.kept_record_count == 2
    assert view.conflicting_structure_groups_excluded == 1
    assert view.conflicting_records_excluded == 2
    assert view.same_target_duplicate_groups_collapsed == 1
    assert view.redundant_same_target_records_collapsed == 1
    assert {record.compound_id for record in view.records} == {"a1", "c1"}
    assert all(record.measured_log_s_mol_l != -0.65 for record in view.records)
    assert view.lineage_hash


def test_frozen_seed_keeps_structural_groups_disjoint_and_reports_domain_counts():
    pytest.importorskip("sklearn")
    result = run_frozen_v2_seed(_records(), seed=7)
    assert result.structural_overlap_count == 0
    assert result.train_count + result.validation_count + result.test_count == len(_records())
    assert result.in_domain_count + result.out_of_domain_count == result.test_count
    assert result.test_rmse >= 0
    assert 0 <= result.ad_threshold <= 1


def test_v2_robustness_is_deterministic_for_fixed_seeds():
    pytest.importorskip("sklearn")
    first = run_v2_robustness(_records(), seeds=(7, 21))
    second = run_v2_robustness(_records(), seeds=(7, 21))
    assert first == second
    assert first["summary"]["test_rmse"]["n"] == 2
    assert first["report_hash"]


def test_dataset_sensitivity_preserves_original_and_records_lineage():
    pytest.importorskip("sklearn")
    records = _records() + (
        SolubilityRecord("dup-same", "OCC", _records()[0].measured_log_s_mol_l),
        SolubilityRecord("dup-conflict", "NCC", _records()[3].measured_log_s_mol_l - 1.0),
    )
    result = run_v2_dataset_sensitivity(records, seed=11)
    metadata = result["curated_view"]
    assert metadata["kept_record_count"] < len(records)
    assert metadata["conflicting_structure_groups_excluded"] >= 1
    assert metadata["lineage_hash"]
    assert result["original"]["structural_overlap_count"] == 0
    assert result["unique_nonconflicting"]["structural_overlap_count"] == 0
    assert result["report_hash"]
