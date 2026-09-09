from __future__ import annotations

from research_os.benchmark.reproducibility import (
    execution_hash,
    normalize_scientific_payload,
    scientific_result_hash,
)


def test_scientific_hash_ignores_insignificant_float_noise_and_legacy_hash_fields():
    first = {
        "metric": 0.9635610970870078,
        "nested": {"report_hash": "legacy-a", "value": 1.23456789012341},
        "run_report_hashes": ["raw-run-a", "raw-run-b"],
    }
    second = {
        "metric": 0.9635610970870081,
        "nested": {"report_hash": "legacy-b", "value": 1.23456789012339},
        "run_report_hashes": ["raw-run-c", "raw-run-d"],
    }
    assert scientific_result_hash(first) == scientific_result_hash(second)


def test_scientific_hash_changes_for_material_numeric_change():
    assert scientific_result_hash({"rmse": 0.80}) != scientific_result_hash({"rmse": 0.81})


def test_normalization_preserves_dataset_and_lineage_hashes():
    payload = {
        "dataset_hash": "dataset-123",
        "lineage_hash": "lineage-456",
        "report_hash": "volatile",
        "run_report_hashes": ["volatile-a", "volatile-b"],
    }
    normalized = normalize_scientific_payload(payload)
    assert normalized["dataset_hash"] == "dataset-123"
    assert normalized["lineage_hash"] == "lineage-456"
    assert "report_hash" not in normalized
    assert "run_report_hashes" not in normalized


def test_execution_hash_binds_scientific_result_to_environment():
    scientific = scientific_result_hash({"rmse": 0.8})
    linux = execution_hash(scientific, {"python": "3.12", "rdkit": "A", "platform": "linux"})
    windows = execution_hash(scientific, {"python": "3.12", "rdkit": "A", "platform": "windows"})
    assert linux != windows
