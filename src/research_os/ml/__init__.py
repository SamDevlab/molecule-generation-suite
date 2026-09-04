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
from research_os.ml.training import CandidateModel, FeatureSchema, TrainingRunManifest
from research_os.ml.golden import GoldenMLResult, run_ml_golden_path
from research_os.ml.promotion import (
    ModelPromotionEngine,
    PromotionDecision,
    PromotionPolicy,
    PromotionStatus,
    promote_candidate,
)
from research_os.ml.real import (
    REAL_FEATURE_SCHEMA,
    REAL_SOLUBILITY_TASK,
    MorganTanimotoApplicabilityDomain,
    PredictionResult,
    RealMLResult,
    ResidualIntervalEstimator,
    RidgeFingerprintModel,
    SplitManifest,
    make_real_split,
    rank_in_domain,
    train_real_solubility_model,
)
from research_os.ml.real_golden import RealGoldenRunResult, run_real_data_golden

__all__ = [
    "ApplicabilityDomain",
    "ApplicabilityDomainResult",
    "CalibrationChecker",
    "DataSplit",
    "CandidateModel",
    "FeatureSchema",
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
    "TrainingRunManifest",
    "GoldenMLResult",
    "run_ml_golden_path",
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
    "REAL_FEATURE_SCHEMA",
    "REAL_SOLUBILITY_TASK",
    "MorganTanimotoApplicabilityDomain",
    "PredictionResult",
    "RealMLResult",
    "ResidualIntervalEstimator",
    "RidgeFingerprintModel",
    "SplitManifest",
    "make_real_split",
    "rank_in_domain",
    "train_real_solubility_model",
    "RealGoldenRunResult",
    "run_real_data_golden",
]
