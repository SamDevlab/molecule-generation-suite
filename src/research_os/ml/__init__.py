"""Central ML validation and model promotion contracts.

This package deliberately contains validation/provenance boundaries, not
domain-specific model training code.  Labs can use it without duplicating
split or promotion logic.
"""

from research_os.ml.metrics import RegressionMetrics, compute_regression_metrics, metric_value
from research_os.ml.registry import ModelRecord, ModelRegistry, ModelStage
from research_os.ml.schema import (
    ApplicabilityDomainResult,
    DataSplit,
    SplitStrategy,
    ValidationGate,
    ValidationReport,
)
from research_os.ml.splitters import (
    SplitError,
    cluster_split,
    external_test,
    group_split,
    random_split,
    scaffold_split,
    source_split,
    split_records,
    temporal_split,
)
from research_os.ml.validation import (
    ApplicabilityDomain,
    CalibrationChecker,
    OutOfDomainScorer,
    PredictionIntervalEstimator,
    validate_regression,
)
from research_os.ml.promotion import (
    ModelPromotionEngine,
    PromotionDecision,
    PromotionPolicy,
    PromotionStatus,
    promote_candidate,
)

__all__ = [
    "ApplicabilityDomain",
    "ApplicabilityDomainResult",
    "CalibrationChecker",
    "DataSplit",
    "ModelPromotionEngine",
    "ModelRecord",
    "ModelRegistry",
    "ModelStage",
    "OutOfDomainScorer",
    "PredictionIntervalEstimator",
    "PromotionDecision",
    "PromotionPolicy",
    "PromotionStatus",
    "promote_candidate",
    "RegressionMetrics",
    "SplitError",
    "SplitStrategy",
    "ValidationGate",
    "ValidationReport",
    "cluster_split",
    "compute_regression_metrics",
    "external_test",
    "group_split",
    "metric_value",
    "random_split",
    "scaffold_split",
    "source_split",
    "split_records",
    "temporal_split",
    "validate_regression",
]
