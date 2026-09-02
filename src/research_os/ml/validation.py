from __future__ import annotations

from typing import Any, Protocol, Sequence

from research_os.core.types import GateStatus
from research_os.ml.metrics import compute_regression_metrics
from research_os.ml.schema import ApplicabilityDomainResult, SplitStrategy, ValidationGate, ValidationReport


class ApplicabilityDomain(Protocol):
    def assess(self, features: Sequence[Any]) -> ApplicabilityDomainResult: ...


class OutOfDomainScorer(Protocol):
    def score(self, features: Sequence[Any]) -> float: ...


class PredictionIntervalEstimator(Protocol):
    def interval(self, features: Sequence[Any]) -> tuple[float, float]: ...


class CalibrationChecker(Protocol):
    def check(self, y_true: Sequence[float], predictions: Sequence[Any]) -> dict[str, Any]: ...


class UnavailableApplicabilityDomain:
    """Explicit placeholder; absence of an AD implementation is not PASS."""

    def assess(self, features: Sequence[Any]) -> ApplicabilityDomainResult:
        return ApplicabilityDomainResult(False, None, "unavailable", "applicability-domain implementation is not configured")


def validate_regression(
    y_true: Sequence[float],
    y_pred: Sequence[float],
    *,
    model_id: str | None = None,
    task: str | None = None,
    split_strategy: SplitStrategy | str = SplitStrategy.RANDOM,
    train_count: int = 0,
    validation_count: int = 0,
    seed: int | None = 42,
    external_test_acceptable: bool | None = None,
    applicability_domain: ApplicabilityDomainResult | None = None,
    out_of_domain_score: float | None = None,
    prediction_interval: dict[str, Any] | None = None,
    calibration: dict[str, Any] | None = None,
) -> ValidationReport:
    try:
        strategy = split_strategy if isinstance(split_strategy, SplitStrategy) else SplitStrategy(str(split_strategy))
    except ValueError as exc:
        return ValidationReport(model_id, task, SplitStrategy.RANDOM, train_count, validation_count, len(y_true), seed, {}, (ValidationGate("GATE-ML-SCHEMA", "ML-SPLIT-001", GateStatus.FAIL, "unsupported split strategy", diagnostics={"split_strategy": str(split_strategy)}),), external_test_acceptable, applicability_domain, out_of_domain_score, prediction_interval, calibration)
    if len(y_true) != len(y_pred) or not y_true:
        return ValidationReport(model_id, task, strategy, train_count, validation_count, len(y_true), seed, {}, (ValidationGate("GATE-ML-INPUT", "ML-INPUT-001", GateStatus.FAIL, "prediction arrays must be non-empty and have equal length", diagnostics={"y_true_count": len(y_true), "y_pred_count": len(y_pred)}),), external_test_acceptable, applicability_domain, out_of_domain_score, prediction_interval, calibration)
    try:
        metrics = compute_regression_metrics(y_true, y_pred).to_dict()
    except (TypeError, ValueError, OverflowError) as exc:
        return ValidationReport(model_id, task, strategy, train_count, validation_count, len(y_true), seed, {}, (ValidationGate("GATE-ML-INPUT", "ML-INPUT-001", GateStatus.FAIL, "regression inputs are not finite numeric values", diagnostics={"error_type": type(exc).__name__, "error": str(exc)}),), external_test_acceptable, applicability_domain, out_of_domain_score, prediction_interval, calibration)
    gates = (ValidationGate("GATE-ML-METRICS", "ML-METRICS-001", GateStatus.PASS, "MAE, RMSE and R2 calculated on the declared split"),)
    return ValidationReport(model_id, task, strategy, train_count, validation_count, len(y_true), seed, metrics, gates, external_test_acceptable, applicability_domain, out_of_domain_score, prediction_interval, calibration)


# Descriptive alias for callers that want to emphasize prediction validation.
validate_regression_predictions = validate_regression
