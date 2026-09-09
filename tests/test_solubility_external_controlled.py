from __future__ import annotations

import math

import pytest

from research_os.benchmark.solubility import SolubilityBenchmarkError
from research_os.benchmark.solubility_external_controlled import (
    EXPECTED_RELIABILITY_METADATA_HASH,
    HIGHER_DISPERSION_GROUPS,
    LOWER_DISPERSION_GROUPS,
    SIMILARITY_BINS,
    TARGET_BINS,
    ControlledObservation,
    _assign_cohort,
    _similarity_bin,
    _target_bin,
    standardize_controlled_error,
)


def _observation(
    *,
    source_id: str,
    cohort: str,
    truth: float,
    prediction: float,
    similarity: float,
    ad_status: str = "ID",
    similarity_bin: str = "[0.4,0.6)",
    target_bin: str = "[-4,-2)",
    group: str | None = None,
) -> ControlledObservation:
    if group is None:
        group = "G2" if cohort == "higher_dispersion" else "G3"
    return ControlledObservation(
        source_id=source_id,
        group=group,
        cohort=cohort,
        truth=truth,
        prediction=prediction,
        max_train_similarity=similarity,
        ad_status=ad_status,
        similarity_bin=similarity_bin,
        target_bin=target_bin,
    )


def test_exp004_cohorts_and_parent_metadata_are_frozen() -> None:
    assert HIGHER_DISPERSION_GROUPS == ("G2", "G4")
    assert LOWER_DISPERSION_GROUPS == ("G3", "G5")
    assert EXPECTED_RELIABILITY_METADATA_HASH == (
        "6cfeceee8f06b8e388fb86b172e0d2bb9c2e701002a530761502c543ad87c0a5"
    )
    assert _assign_cohort("G2") == "higher_dispersion"
    assert _assign_cohort("G4") == "higher_dispersion"
    assert _assign_cohort("G3") == "lower_dispersion"
    assert _assign_cohort("G5") == "lower_dispersion"
    assert _assign_cohort("G1") is None
    with pytest.raises(SolubilityBenchmarkError, match="unexpected reliability group"):
        _assign_cohort("G9")


def test_exp004_frozen_bins_cover_boundaries_deterministically() -> None:
    assert [label for _, _, label in SIMILARITY_BINS] == [
        "[0.0,0.4)",
        "[0.4,0.6)",
        "[0.6,0.8)",
        "[0.8,1.0]",
    ]
    assert [label for _, _, label in TARGET_BINS] == [
        "(-inf,-6)",
        "[-6,-4)",
        "[-4,-2)",
        "[-2,0)",
        "[0,+inf)",
    ]
    assert _similarity_bin(0.0) == "[0.0,0.4)"
    assert _similarity_bin(0.4) == "[0.4,0.6)"
    assert _similarity_bin(0.6) == "[0.6,0.8)"
    assert _similarity_bin(0.8) == "[0.8,1.0]"
    assert _similarity_bin(1.0) == "[0.8,1.0]"
    assert _target_bin(-6.0001) == "(-inf,-6)"
    assert _target_bin(-6.0) == "[-6,-4)"
    assert _target_bin(-4.0) == "[-4,-2)"
    assert _target_bin(-2.0) == "[-2,0)"
    assert _target_bin(0.0) == "[0,+inf)"


def test_controlled_standardization_uses_common_minimum_support_weights() -> None:
    records = [
        _observation(source_id="h1", cohort="higher_dispersion", truth=0.0, prediction=2.0, similarity=0.5),
        _observation(source_id="h2", cohort="higher_dispersion", truth=0.0, prediction=2.0, similarity=0.5),
        _observation(source_id="l1", cohort="lower_dispersion", truth=0.0, prediction=1.0, similarity=0.5),
        _observation(source_id="l2", cohort="lower_dispersion", truth=0.0, prediction=1.0, similarity=0.5),
        _observation(source_id="l3", cohort="lower_dispersion", truth=0.0, prediction=1.0, similarity=0.5),
        _observation(source_id="l4", cohort="lower_dispersion", truth=0.0, prediction=1.0, similarity=0.5),
        _observation(
            source_id="h3",
            cohort="higher_dispersion",
            truth=-5.0,
            prediction=-2.0,
            similarity=0.2,
            ad_status="OOD",
            similarity_bin="[0.0,0.4)",
            target_bin="[-6,-4)",
        ),
        _observation(
            source_id="l5",
            cohort="lower_dispersion",
            truth=-5.0,
            prediction=-4.0,
            similarity=0.2,
            ad_status="OOD",
            similarity_bin="[0.0,0.4)",
            target_bin="[-6,-4)",
        ),
    ]

    result = standardize_controlled_error(records)
    assert result.coverage.shared_cell_count == 2
    assert result.coverage.matching_support == 3
    assert result.metrics.higher_dispersion_mae == pytest.approx(7 / 3)
    assert result.metrics.lower_dispersion_mae == pytest.approx(1.0)
    assert result.metrics.higher_dispersion_rmse == pytest.approx(math.sqrt(17 / 3))
    assert result.metrics.lower_dispersion_rmse == pytest.approx(1.0)
    assert result.metrics.mae_delta_higher_minus_lower == pytest.approx(4 / 3)
    assert result.metrics.rmse_delta_higher_minus_lower > 0


def test_nonshared_cells_are_excluded_from_primary_standardization_but_counted_in_total_coverage() -> None:
    shared_high = _observation(source_id="h1", cohort="higher_dispersion", truth=-3.0, prediction=-2.0, similarity=0.5)
    shared_low = _observation(source_id="l1", cohort="lower_dispersion", truth=-3.0, prediction=-2.5, similarity=0.5)
    exclusive_high = _observation(
        source_id="h2",
        cohort="higher_dispersion",
        truth=0.5,
        prediction=5.0,
        similarity=0.9,
        ad_status="ID",
        similarity_bin="[0.8,1.0]",
        target_bin="[0,+inf)",
    )

    result = standardize_controlled_error([shared_high, shared_low, exclusive_high])
    assert result.coverage.total_higher_dispersion == 2
    assert result.coverage.total_lower_dispersion == 1
    assert result.coverage.shared_cell_higher_dispersion == 1
    assert result.coverage.shared_cell_lower_dispersion == 1
    assert result.coverage.shared_cell_fraction_higher_dispersion == pytest.approx(0.5)
    assert result.coverage.shared_cell_fraction_lower_dispersion == pytest.approx(1.0)
    assert result.coverage.matching_support == 1
    assert result.metrics.higher_dispersion_mae == pytest.approx(1.0)
    assert result.metrics.lower_dispersion_mae == pytest.approx(0.5)


def test_controlled_standardization_fails_closed_without_shared_cells() -> None:
    high = _observation(source_id="h1", cohort="higher_dispersion", truth=-3.0, prediction=-2.0, similarity=0.5)
    low = _observation(
        source_id="l1",
        cohort="lower_dispersion",
        truth=0.5,
        prediction=0.0,
        similarity=0.9,
        similarity_bin="[0.8,1.0]",
        target_bin="[0,+inf)",
    )
    with pytest.raises(SolubilityBenchmarkError, match="no shared confounder cells"):
        standardize_controlled_error([high, low])
