"""Tiny ML-core fixture using an explicitly synthetic, non-molecular target."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from research_os.artifacts import ModelArtifactManifest
from research_os.core.types import EvidenceLevel
from research_os.datasets import DatasetManifest, DatasetSourceType
from research_os.ml.promotion import ModelPromotionEngine, PromotionDecision
from research_os.ml.schema import SplitStrategy, ValidationReport
from research_os.ml.training import CandidateModel, FeatureSchema, TrainingRunManifest
from research_os.ml.validation import validate_regression


@dataclass(frozen=True)
class GoldenMLResult:
    dataset: DatasetManifest
    feature_schema: FeatureSchema
    training_run: TrainingRunManifest
    champion: ModelArtifactManifest
    candidate: ModelArtifactManifest
    candidate_model: CandidateModel
    validation: ValidationReport
    decision: PromotionDecision


def run_ml_golden_path() -> GoldenMLResult:
    records = ({"feature_a": 0.0, "feature_b": 1.0, "fixture_target": 1.0}, {"feature_a": 1.0, "feature_b": 0.0, "fixture_target": 2.0}, {"feature_a": 2.0, "feature_b": 1.0, "fixture_target": 3.0}, {"feature_a": 3.0, "feature_b": 0.0, "fixture_target": 4.0})
    dataset = DatasetManifest.from_records(dataset_id="golden-ml-fixture", version="1", schema_id="golden-ml-schema-v1", records=records, source_types=(DatasetSourceType.TEST_SYNTHETIC,), evidence_levels=(EvidenceLevel.TEST_SYNTHETIC,), synthetic_fraction=1.0, notes="Synthetic fixture target; not a molecular property or experimental ground truth.")
    feature_schema = FeatureSchema("golden-features-v1", ("feature_a", "feature_b"), "Non-molecular fixture features")
    training_run = TrainingRunManifest.create(model_id="golden-candidate", task="fixture_regression", dataset_id=dataset.dataset_id, dataset_hash=dataset.sha256, feature_schema_id=feature_schema.feature_schema_id, split_strategy=SplitStrategy.GROUP, train_count=2, validation_count=1, test_count=1, seed=42, hyperparameters={"estimator": "deterministic_fixture", "regularization": 0.1}, metrics={"MAE": 0.4, "RMSE": 0.45, "R2": 0.8}, framework="test_fixture", framework_version="1", git_commit="fixture", environment_id="ENV-GOLDEN")
    champion = ModelArtifactManifest(model_id="golden-champion", task="fixture_regression", training_run_id="TRN-GOLDEN-CHAMPION", dataset_id=dataset.dataset_id, dataset_hash=dataset.sha256, feature_schema_id=feature_schema.feature_schema_id, split_strategy=SplitStrategy.GROUP.value, train_count=2, validation_count=1, test_count=1, seed=42, metrics={"MAE": 0.2, "RMSE": 0.25, "R2": 0.9}, framework="test_fixture", framework_version="1", git_commit="fixture")
    candidate = ModelArtifactManifest(model_id=training_run.model_id, task=training_run.task, training_run_id=training_run.training_run_id, dataset_id=dataset.dataset_id, dataset_hash=dataset.sha256, feature_schema_id=feature_schema.feature_schema_id, split_strategy=training_run.split_strategy, train_count=training_run.train_count, validation_count=training_run.validation_count, test_count=training_run.test_count, seed=training_run.seed, metrics=training_run.metrics, framework=training_run.framework, framework_version=training_run.framework_version, git_commit=training_run.git_commit)
    candidate_model = CandidateModel(manifest_id=training_run.training_run_id, model_manifest_id=candidate.model_id, training_run_id=training_run.training_run_id)
    validation = validate_regression([1.0, 2.0, 3.0, 4.0], [1.1, 1.9, 3.2, 3.8], model_id=candidate.model_id, task=candidate.task, split_strategy=SplitStrategy.GROUP, train_count=2, validation_count=1, seed=42, external_test_acceptable=True)
    decision = ModelPromotionEngine().evaluate(candidate, champion, validation=validation)
    return GoldenMLResult(dataset, feature_schema, training_run, champion, candidate, candidate_model, validation, decision)
