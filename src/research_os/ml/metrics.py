from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Iterable, Mapping


@dataclass(frozen=True)
class RegressionMetrics:
    """Regression metrics; R2 remains a score and is never a reliability percent."""

    mae: float
    rmse: float
    r2: float

    def to_dict(self) -> dict[str, float]:
        return {"MAE": self.mae, "RMSE": self.rmse, "R2": self.r2}

    @property
    def MAE(self) -> float:  # noqa: N802 - mirrors the scientific metric name
        return self.mae

    @property
    def RMSE(self) -> float:  # noqa: N802 - mirrors the scientific metric name
        return self.rmse

    @property
    def R2(self) -> float:  # noqa: N802 - mirrors the scientific metric name
        return self.r2


def compute_regression_metrics(y_true: Iterable[float], y_pred: Iterable[float]) -> RegressionMetrics:
    actual = [float(value) for value in y_true]
    predicted = [float(value) for value in y_pred]
    if not actual:
        raise ValueError("regression metrics require at least one observation")
    if len(actual) != len(predicted):
        raise ValueError("y_true and y_pred must have equal length")
    if any(not isfinite(value) for value in (*actual, *predicted)):
        raise ValueError("regression inputs must be finite")
    errors = [estimate - truth for truth, estimate in zip(actual, predicted)]
    mae = sum(abs(error) for error in errors) / len(errors)
    rmse = sqrt(sum(error * error for error in errors) / len(errors))
    mean = sum(actual) / len(actual)
    total = sum((truth - mean) ** 2 for truth in actual)
    residual = sum(error * error for error in errors)
    # This matches the useful limiting behavior of common ML libraries while
    # avoiding a division-by-zero result for constant targets.
    r2 = 1.0 if residual == 0 else (0.0 if total == 0 else 1.0 - residual / total)
    return RegressionMetrics(mae=mae, rmse=rmse, r2=r2)


def metric_value(metrics: Mapping[str, float], name: str) -> float | None:
    """Read canonical or legacy metric casing without changing its meaning."""
    normalized = name.strip().lower().replace("²", "2")
    for key, value in metrics.items():
        if str(key).strip().lower().replace("²", "2") == normalized:
            return float(value)
    return None
