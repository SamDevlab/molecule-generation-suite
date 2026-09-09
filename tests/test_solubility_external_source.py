from __future__ import annotations

import math

import pytest

from research_os.benchmark.solubility import SolubilityBenchmarkError
from research_os.benchmark.solubility_external_source import (
    MIN_CONTRIBUTING_SOURCES,
    MIN_MATCHING_SUPPORT,
    MIN_SHARED_FRACTION,
    SourceAwareObservation,
    source_dataset_from_id,
    standardize_source_aware_error,
    summarize_sources,
)


def _observation(
    *,
    source_id: str,
    source_dataset: str,
    cohort: str,
    truth: float = -3.0,
    prediction: float = -2.0,
    similarity: float = 0.5,
    ad_status: str = "ID",
    similarity_bin: str = "[0.4,0.6)",
    target_bin: str = "[-4,-2)",
    group: str | None = None,
) -> SourceAwareObservation:
    if group is None:
        group = "G2" if cohort == "higher_dispersion" else "G3"
    return SourceAwareObservation(
        source_id=source_id,
        source_dataset=source_dataset,
        group=group,
        cohort=cohort,
        truth=truth,
        prediction=prediction,
        max_train_similarity=similarity,
        ad_status=ad_status,
        similarity_bin=similarity_bin,
        target_bin=target_bin,
    )


def test_exp005_source_parser_is_frozen_to_a_through_i_prefixes() -> None:
    for prefix in "ABCDEFGHI":
        assert source_dataset_from_id(f"{prefix}-123") == prefix

    for invalid in ("J-1", "A1", "a-1", "row-3", "", "AA-1"):
        with pytest.raises(SolubilityBenchmarkError, match="source prefix A-I"):
            source_dataset_from_id(invalid)


def test_exp005_support_thresholds_are_frozen() -> None:
    assert MIN_MATCHING_SUPPORT == 50
    assert MIN_SHARED_FRACTION == 0.50
    assert MIN_CONTRIBUTING_SOURCES == 2


def test_source_dimension_prevents_cross_source_cell_pooling() -> None:
    records = [
        _observation(
            source_id="A-1",
            source_dataset="A",
            cohort="higher_dispersion",
            prediction=-1.0,
        ),
        _observation(
            source_id="B-1",
            source_dataset="B",
            cohort="lower_dispersion",
            prediction=-2.5,
        ),
    ]
    with pytest.raises(SolubilityBenchmarkError, match="no shared source-aware cells"):
        standardize_source_aware_error(records)


def test_source_aware_standardization_uses_common_weights_and_reports_insufficient_overlap() -> None:
    records = [
        _observation(
            source_id="A-h1",
            source_dataset="A",
            cohort="higher_dispersion",
            truth=0.0,
            prediction=2.0,
        ),
        _observation(
            source_id="A-h2",
            source_dataset="A",
            cohort="higher_dispersion",
            truth=0.0,
            prediction=2.0,
        ),
        _observation(
            source_id="A-l1",
            source_dataset="A",
            cohort="lower_dispersion",
            truth=0.0,
            prediction=1.0,
        ),
        _observation(
            source_id="A-l2",
            source_dataset="A",
            cohort="lower_dispersion",
            truth=0.0,
            prediction=1.0,
        ),
        _observation(
            source_id="A-l3",
            source_dataset="A",
            cohort="lower_dispersion",
            truth=0.0,
            prediction=1.0,
        ),
    ]

    result = standardize_source_aware_error(records)
    assert result.coverage.shared_cell_count == 1
    assert result.coverage.matching_support == 2
    assert result.coverage.contributing_sources == ("A",)
    assert result.coverage.interpretation_status == "INSUFFICIENT_OVERLAP"
    assert result.metrics.higher_dispersion_mae == pytest.approx(2.0)
    assert result.metrics.lower_dispersion_mae == pytest.approx(1.0)
    assert result.metrics.higher_dispersion_rmse == pytest.approx(2.0)
    assert result.metrics.lower_dispersion_rmse == pytest.approx(1.0)


def test_source_aware_standardization_reaches_supported_only_at_frozen_boundary() -> None:
    records: list[SourceAwareObservation] = []
    for source in ("A", "B"):
        for index in range(25):
            records.append(
                _observation(
                    source_id=f"{source}-h{index}",
                    source_dataset=source,
                    cohort="higher_dispersion",
                    truth=0.0,
                    prediction=2.0,
                )
            )
            records.append(
                _observation(
                    source_id=f"{source}-l{index}",
                    source_dataset=source,
                    cohort="lower_dispersion",
                    truth=0.0,
                    prediction=1.0,
                )
            )

    result = standardize_source_aware_error(records)
    assert result.coverage.matching_support == 50
    assert result.coverage.shared_cell_fraction_higher_dispersion == pytest.approx(1.0)
    assert result.coverage.shared_cell_fraction_lower_dispersion == pytest.approx(1.0)
    assert result.coverage.contributing_sources == ("A", "B")
    assert result.coverage.interpretation_status == "SUPPORTED"
    assert result.metrics.mae_delta_higher_minus_lower == pytest.approx(1.0)
    assert result.metrics.rmse_delta_higher_minus_lower == pytest.approx(1.0)


def test_source_diagnostics_remain_separate_and_do_not_require_both_cohorts() -> None:
    records = [
        _observation(
            source_id="A-h1",
            source_dataset="A",
            cohort="higher_dispersion",
            truth=-4.0,
            prediction=-2.0,
            similarity=0.2,
            ad_status="OOD",
            similarity_bin="[0.0,0.4)",
            target_bin="[-6,-4)",
        ),
        _observation(
            source_id="A-l1",
            source_dataset="A",
            cohort="lower_dispersion",
            truth=-4.0,
            prediction=-3.0,
            similarity=0.6,
            similarity_bin="[0.6,0.8)",
            target_bin="[-6,-4)",
        ),
        _observation(
            source_id="B-h1",
            source_dataset="B",
            cohort="higher_dispersion",
            truth=-2.0,
            prediction=-1.5,
            similarity=0.5,
            target_bin="[-2,0)",
        ),
    ]

    summaries = summarize_sources(records)
    assert [item.source_dataset for item in summaries] == ["A", "B"]

    source_a = summaries[0]
    assert source_a.higher_dispersion is not None
    assert source_a.lower_dispersion is not None
    assert source_a.raw_mae_delta_higher_minus_lower == pytest.approx(1.0)
    assert source_a.raw_rmse_delta_higher_minus_lower == pytest.approx(1.0)
    assert source_a.higher_dispersion.out_of_domain_count == 1
    assert source_a.lower_dispersion.in_domain_count == 1

    source_b = summaries[1]
    assert source_b.higher_dispersion is not None
    assert source_b.lower_dispersion is None
    assert source_b.raw_mae_delta_higher_minus_lower is None
    assert source_b.raw_rmse_delta_higher_minus_lower is None


def test_source_aware_rmse_uses_weighted_mse_not_weighted_cell_rmse() -> None:
    records = [
        _observation(
            source_id="A-h1",
            source_dataset="A",
            cohort="higher_dispersion",
            truth=0.0,
            prediction=1.0,
        ),
        _observation(
            source_id="A-l1",
            source_dataset="A",
            cohort="lower_dispersion",
            truth=0.0,
            prediction=1.0,
        ),
        _observation(
            source_id="B-h1",
            source_dataset="B",
            cohort="higher_dispersion",
            truth=-5.0,
            prediction=-2.0,
            similarity=0.2,
            ad_status="OOD",
            similarity_bin="[0.0,0.4)",
            target_bin="[-6,-4)",
        ),
        _observation(
            source_id="B-l1",
            source_dataset="B",
            cohort="lower_dispersion",
            truth=-5.0,
            prediction=-4.0,
            similarity=0.2,
            ad_status="OOD",
            similarity_bin="[0.0,0.4)",
            target_bin="[-6,-4)",
        ),
    ]

    result = standardize_source_aware_error(records)
    assert result.metrics.higher_dispersion_rmse == pytest.approx(math.sqrt(5.0))
    assert result.metrics.lower_dispersion_rmse == pytest.approx(1.0)
