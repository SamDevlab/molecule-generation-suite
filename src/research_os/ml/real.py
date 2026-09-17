"""Small, dependency-light real-data molecular ML path for v1.6.

This is intentionally a first empirical baseline, not a production predictor:
Morgan fingerprints feed a NumPy ridge regressor, validation uses an explicit
scaffold split, and uncertainty is a residual-calibrated prediction interval.
The model never turns an out-of-domain prediction into a normal ranked result.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from math import isfinite
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import uuid

import numpy as np

from research_os.artifacts import ModelArtifactManifest
from research_os.core.hashing import sha256_json
from research_os.core.types import EvidenceLevel, GateStatus
from research_os.datasets import DatasetManifest, dataset_ground_truth_gate
from research_os.molecule.features import MorganFeaturizer
from research_os.ml.metrics import compute_regression_metrics
from research_os.ml.schema import ApplicabilityDomainResult, DataSplit, SplitStrategy, ValidationReport
from research_os.ml.splitters import scaffold_split, split_records
from research_os.ml.training import CandidateModel, FeatureSchema, TrainingRunManifest
from research_os.ml.validation import validate_regression


REAL_SOLUBILITY_TASK = "aqueous_solubility_logS"
REAL_FEATURE_SCHEMA = FeatureSchema(
    "MOL-MORGAN-R2-2048-v1",
    ("morgan_fingerprint_r2_2048",),
    "Morgan circular fingerprint radius 2, 2048 bits; ML representation only.",
    version="1",
)


@dataclass(frozen=True)
class SplitManifest:
    """Persisted identity lists for a leakage-auditable dataset split."""

    split_id: str
    dataset_id: str
    dataset_hash: str
    strategy: SplitStrategy | str
    seed: int | None
    feature_schema_id: str
    train_ids: tuple[str, ...]
    validation_ids: tuple[str, ...]
    test_ids: tuple[str, ...]
    external_test_ids: tuple[str, ...] = ()
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        strategy = self.strategy if isinstance(self.strategy, SplitStrategy) else SplitStrategy(str(self.strategy))
        object.__setattr__(self, "strategy", strategy)
        for name in ("train_ids", "validation_ids", "test_ids", "external_test_ids"):
            values = tuple(str(value) for value in getattr(self, name))
            if len(values) != len(set(values)):
                raise ValueError(f"{name} contains duplicate record ids")
            object.__setattr__(self, name, values)
        groups = {name: set(getattr(self, name)) for name in ("train_ids", "validation_ids", "test_ids", "external_test_ids")}
        names = tuple(groups)
        for left_index, left in enumerate(names):
            for right in names[left_index + 1 :]:
                overlap = groups[left] & groups[right]
                if overlap:
                    raise ValueError(f"split manifest has overlapping ids: {left}/{right}: {sorted(overlap)[:3]}")

    @property
    def counts(self) -> dict[str, int]:
        return {"train": len(self.train_ids), "validation": len(self.validation_ids), "test": len(self.test_ids), "external_test": len(self.external_test_ids)}

    @classmethod
    def from_data_split(
        cls,
        data_split: DataSplit[Mapping[str, Any]],
        *,
        dataset: DatasetManifest,
        feature_schema: FeatureSchema = REAL_FEATURE_SCHEMA,
        split_id: str | None = None,
        external_test_ids: Sequence[str] = (),
    ) -> "SplitManifest":
        def record_id(record: Mapping[str, Any]) -> str:
            value = record.get("compound_id") or record.get("ID") or record.get("id")
            if value is None:
                raise ValueError("real molecular records require compound_id or ID")
            return str(value)

        return cls(
            split_id=split_id or f"SPLIT-{uuid.uuid4().hex[:12].upper()}",
            dataset_id=dataset.dataset_id,
            dataset_hash=dataset.sha256,
            strategy=data_split.strategy,
            seed=data_split.seed,
            feature_schema_id=feature_schema.feature_schema_id,
            train_ids=tuple(record_id(record) for record in data_split.train),
            validation_ids=tuple(record_id(record) for record in data_split.validation),
            test_ids=tuple(record_id(record) for record in data_split.test),
            external_test_ids=tuple(str(value) for value in external_test_ids),
            metadata=dict(data_split.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["strategy"] = self.strategy.value
        data["train_ids"] = list(self.train_ids)
        data["validation_ids"] = list(self.validation_ids)
        data["test_ids"] = list(self.test_ids)
        data["external_test_ids"] = list(self.external_test_ids)
        data["counts"] = self.counts
        return data

    @property
    def manifest_hash(self) -> str:
        return sha256_json(self.to_dict())

    def write(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({**self.to_dict(), "manifest_hash": self.manifest_hash}, indent=2, ensure_ascii=False), encoding="utf-8")
        return target


@dataclass(frozen=True)
class PredictionResult:
    """One prediction plus the provenance and OOD decision required to use it."""

    prediction: float
    uncertainty: float
    ood_score: float
    in_domain: bool
    model_id: str
    dataset_id: str
    feature_schema_id: str
    run_id: str
    status: str = "IN_DOMAIN"
    prediction_interval: tuple[float, float] | None = None
    applicability_domain_method: str = "morgan_tanimoto_to_training_max"
    reason: str = ""

    @property
    def rankable(self) -> bool:
        return self.in_domain and self.status != GateStatus.OUT_OF_DOMAIN.value

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["prediction_interval"] = list(self.prediction_interval) if self.prediction_interval is not None else None
        data["rankable"] = self.rankable
        return data


@dataclass
class MorganTanimotoApplicabilityDomain:
    """Maximum Morgan/Tanimoto similarity to the training set."""

    training_fingerprints: np.ndarray
    threshold: float = 0.4
    method: str = "morgan_tanimoto_to_training_max"

    def __post_init__(self) -> None:
        matrix = np.asarray(self.training_fingerprints, dtype=np.uint8)
        if matrix.ndim != 2 or matrix.shape[0] == 0:
            raise ValueError("applicability domain requires a non-empty 2-D training fingerprint matrix")
        if not 0.0 <= float(self.threshold) <= 1.0:
            raise ValueError("applicability-domain threshold must be in [0,1]")
        self.training_fingerprints = matrix

    def assess(self, features: Sequence[Any]) -> ApplicabilityDomainResult:
        query = np.asarray(features, dtype=np.uint8).reshape(-1)
        if query.shape[0] != self.training_fingerprints.shape[1]:
            raise ValueError("query fingerprint width does not match the training feature width")
        query_on = query.astype(bool)
        train_on = self.training_fingerprints.astype(bool)
        intersections = np.logical_and(train_on, query_on).sum(axis=1)
        unions = np.logical_or(train_on, query_on).sum(axis=1)
        similarities = np.divide(intersections, unions, out=np.ones_like(intersections, dtype=float), where=unions != 0)
        score = float(np.max(similarities))
        return ApplicabilityDomainResult(score >= self.threshold, score, self.method, f"maximum training-set Tanimoto similarity={score:.4f}; threshold={self.threshold:.4f}")

    def assess_smiles(self, smiles: str, featurizer: MorganFeaturizer | None = None) -> ApplicabilityDomainResult:
        return self.assess((featurizer or MorganFeaturizer()).transform_one(smiles))


@dataclass(frozen=True)
class ResidualIntervalEstimator:
    """Absolute-residual quantile interval; it is not a certainty statement."""

    quantile: float = 0.9
    radius: float = 0.0
    calibration_count: int = 0
    calibration_source: str = "unfitted"
    method: str = "absolute_residual_quantile"

    @classmethod
    def fit(cls, y_true: Sequence[float], y_pred: Sequence[float], *, quantile: float = 0.9, source: str = "validation") -> "ResidualIntervalEstimator":
        if not 0.0 < quantile <= 1.0:
            raise ValueError("interval quantile must be in (0,1]")
        if len(y_true) != len(y_pred) or len(y_true) == 0:
            raise ValueError("interval calibration requires equal, non-empty arrays")
        residuals = np.abs(np.asarray(y_true, dtype=float) - np.asarray(y_pred, dtype=float))
        radius = float(np.quantile(residuals, quantile))
        return cls(quantile, radius, len(residuals), source)

    def interval(self, prediction: float) -> tuple[float, float]:
        if self.calibration_count <= 0:
            raise ValueError("interval estimator has not been calibrated")
        return float(prediction - self.radius), float(prediction + self.radius)

    def to_dict(self) -> dict[str, Any]:
        return {"method": self.method, "quantile": self.quantile, "radius": self.radius, "calibration_count": self.calibration_count, "calibration_source": self.calibration_source, "interpretation": "residual-calibrated prediction interval; not certainty"}


class RidgeFingerprintModel:
    """NumPy-only ridge model over binary Morgan fingerprints."""

    def __init__(self, *, model_id: str, dataset_id: str, feature_schema_id: str, run_id: str, coefficients: np.ndarray, intercept: float, applicability_domain: MorganTanimotoApplicabilityDomain, interval_estimator: ResidualIntervalEstimator, featurizer: MorganFeaturizer | None = None):
        self.model_id = model_id
        self.dataset_id = dataset_id
        self.feature_schema_id = feature_schema_id
        self.run_id = run_id
        self.coefficients = np.asarray(coefficients, dtype=float)
        self.intercept = float(intercept)
        self.applicability_domain = applicability_domain
        self.interval_estimator = interval_estimator
        self.featurizer = featurizer or MorganFeaturizer()

    def predict_value(self, features: Sequence[Any]) -> float:
        value = float(self.intercept + np.asarray(features, dtype=float).reshape(-1) @ self.coefficients)
        if not isfinite(value):
            raise ValueError("model produced a non-finite prediction")
        return value

    def predict(self, smiles: str) -> PredictionResult:
        features = self.featurizer.transform_one(smiles)
        prediction = self.predict_value(features)
        ad = self.applicability_domain.assess(features)
        uncertainty = float(self.interval_estimator.radius)
        interval = self.interval_estimator.interval(prediction)
        status = "IN_DOMAIN" if ad.in_domain else GateStatus.OUT_OF_DOMAIN.value
        reason = "prediction may be used for in-domain analysis" if ad.in_domain else "out-of-domain prediction is retained for audit only and excluded from normal ranking"
        return PredictionResult(prediction, uncertainty, float(1.0 - (ad.score or 0.0)), ad.in_domain, self.model_id, self.dataset_id, self.feature_schema_id, self.run_id, status, interval, ad.method, reason)

    def predict_many(self, smiles_values: Iterable[str]) -> tuple[PredictionResult, ...]:
        return tuple(self.predict(smiles) for smiles in smiles_values)


def rank_in_domain(predictions: Iterable[PredictionResult]) -> tuple[PredictionResult, ...]:
    """Return only rankable predictions; OUT_OF_DOMAIN entries are excluded."""

    return tuple(sorted((item for item in predictions if item.rankable), key=lambda item: item.prediction))


@dataclass(frozen=True)
class RealMLResult:
    dataset: DatasetManifest
    feature_schema: FeatureSchema
    split: SplitManifest
    training_run: TrainingRunManifest
    candidate_model: CandidateModel
    model_artifact: ModelArtifactManifest
    champion: ModelArtifactManifest
    model: RidgeFingerprintModel
    validation: ValidationReport
    test_predictions: tuple[PredictionResult, ...]
    external_test_acceptable: bool
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset.to_dict(),
            "feature_schema": self.feature_schema.to_dict(),
            "split": self.split.to_dict(),
            "training_run": self.training_run.to_dict(),
            "candidate_model": self.candidate_model.to_dict(),
            "model_artifact": self.model_artifact.to_dict(),
            "champion": self.champion.to_dict(),
            "validation": self.validation.to_dict(),
            "test_predictions": [item.to_dict() for item in self.test_predictions],
            "external_test_acceptable": self.external_test_acceptable,
            "notes": list(self.notes),
        }


def _record_id(record: Mapping[str, Any]) -> str:
    return str(record.get("compound_id") or record.get("ID") or record.get("id"))


def _target(record: Mapping[str, Any]) -> float:
    return float(record.get("target"))


def _fingerprints(records: Sequence[Mapping[str, Any]], featurizer: MorganFeaturizer) -> np.ndarray:
    return np.vstack([featurizer.transform_one(str(record["smiles"])) for record in records])


def _fit_ridge(features: np.ndarray, targets: np.ndarray, alpha: float) -> tuple[np.ndarray, float]:
    if features.ndim != 2 or len(features) != len(targets) or not len(features):
        raise ValueError("ridge training requires non-empty, aligned feature and target arrays")
    augmented = np.column_stack((np.ones(len(features)), features.astype(float)))
    penalty = np.eye(augmented.shape[1], dtype=float) * float(alpha)
    penalty[0, 0] = 0.0
    normal = augmented.T @ augmented + penalty
    rhs = augmented.T @ targets.astype(float)
    try:
        weights = np.linalg.solve(normal, rhs)
    except np.linalg.LinAlgError:
        weights = np.linalg.pinv(normal) @ rhs
    return weights[1:], float(weights[0])


def make_real_split(
    records: Sequence[Mapping[str, Any]],
    dataset: DatasetManifest,
    *,
    strategy: SplitStrategy | str = SplitStrategy.SCAFFOLD,
    validation_size: float = 0.1,
    test_size: float = 0.2,
    seed: int = 42,
    feature_schema: FeatureSchema = REAL_FEATURE_SCHEMA,
    split_id: str | None = None,
) -> tuple[DataSplit[Mapping[str, Any]], SplitManifest]:
    selected = SplitStrategy(strategy) if not isinstance(strategy, SplitStrategy) else strategy
    data_split = scaffold_split(records, validation_size=validation_size, test_size=test_size, seed=seed) if selected == SplitStrategy.SCAFFOLD else split_records(records, selected, validation_size=validation_size, test_size=test_size, seed=seed)
    if not data_split.train or not data_split.test:
        raise ValueError(f"real-data split must contain non-empty train and test sets: {data_split.counts()}")
    manifest = SplitManifest.from_data_split(data_split, dataset=dataset, feature_schema=feature_schema, split_id=split_id)
    return data_split, manifest


def train_real_solubility_model(
    records: Sequence[Mapping[str, Any]],
    dataset: DatasetManifest,
    output_root: str | Path,
    *,
    data_split: DataSplit[Mapping[str, Any]] | None = None,
    split_manifest: SplitManifest | None = None,
    feature_schema: FeatureSchema = REAL_FEATURE_SCHEMA,
    model_id: str | None = None,
    training_run_id: str | None = None,
    seed: int = 42,
    alpha: float = 1.0,
    external_test_acceptable: bool = False,
    environment_id: str | None = None,
    git_commit: str | None = None,
) -> RealMLResult:
    """Train and validate a first real empirical molecular target baseline."""

    data_gate = dataset_ground_truth_gate(dataset)
    if data_gate.status != GateStatus.PASS:
        raise ValueError(f"real ML requires an experimental/curated dataset: {data_gate.reason}")
    if data_split is None or split_manifest is None:
        data_split, split_manifest = make_real_split(records, dataset, seed=seed, feature_schema=feature_schema)
    if split_manifest.dataset_hash != dataset.sha256:
        raise ValueError("split manifest dataset hash does not match the training dataset")
    train = tuple(data_split.train)
    validation_records = tuple(data_split.validation)
    test = tuple(data_split.test)
    featurizer = MorganFeaturizer()
    x_train = _fingerprints(train, featurizer)
    y_train = np.asarray([_target(record) for record in train], dtype=float)
    coefficients, intercept = _fit_ridge(x_train, y_train, alpha)
    model_id = model_id or f"MODEL-{dataset.dataset_id.upper()}-{sha256_json({'dataset': dataset.sha256, 'seed': seed, 'alpha': alpha})[:10].upper()}"
    training_run_id = training_run_id or f"TRN-{model_id.removeprefix('MODEL-')}"
    ad = MorganTanimotoApplicabilityDomain(x_train)
    provisional_interval = ResidualIntervalEstimator.fit(y_train, np.asarray([intercept + row @ coefficients for row in x_train]), source="training_fallback") if not validation_records else None
    if validation_records:
        x_validation = _fingerprints(validation_records, featurizer)
        y_validation = np.asarray([_target(record) for record in validation_records], dtype=float)
        validation_values = np.asarray([intercept + row @ coefficients for row in x_validation], dtype=float)
        interval_estimator = ResidualIntervalEstimator.fit(y_validation, validation_values, source="validation")
    else:
        x_validation = np.empty((0, x_train.shape[1]), dtype=np.uint8)
        y_validation = np.asarray([], dtype=float)
        validation_values = np.asarray([], dtype=float)
        interval_estimator = provisional_interval
    assert interval_estimator is not None
    model = RidgeFingerprintModel(model_id=model_id, dataset_id=dataset.dataset_id, feature_schema_id=feature_schema.feature_schema_id, run_id=training_run_id, coefficients=coefficients, intercept=intercept, applicability_domain=ad, interval_estimator=interval_estimator, featurizer=featurizer)
    x_test = _fingerprints(test, featurizer)
    y_test = np.asarray([_target(record) for record in test], dtype=float)
    test_values = np.asarray([model.predict_value(row) for row in x_test], dtype=float)
    test_predictions = tuple(model.predict(str(record["smiles"])) for record in test)
    test_ad_scores = [1.0 - prediction.ood_score for prediction in test_predictions]
    aggregate_ad = ApplicabilityDomainResult(all(item.in_domain for item in test_predictions), min(test_ad_scores), ad.method, f"{sum(item.in_domain for item in test_predictions)}/{len(test_predictions)} held-out molecules meet the Tanimoto threshold")
    intervals = [prediction.prediction_interval for prediction in test_predictions]
    coverage = sum(lower <= actual <= upper for actual, (lower, upper) in zip(y_test, intervals)) / len(intervals)
    calibration = {**interval_estimator.to_dict(), "test_coverage_observed": coverage, "interpretation": "observed coverage on this held-out split; not certainty"}
    validation_report = validate_regression(y_test.tolist(), test_values.tolist(), model_id=model_id, task=REAL_SOLUBILITY_TASK, split_strategy=split_manifest.strategy, train_count=len(train), validation_count=len(validation_records), seed=seed, external_test_acceptable=external_test_acceptable, applicability_domain=aggregate_ad, out_of_domain_score=float(1.0 - aggregate_ad.score) if aggregate_ad.score is not None else None, prediction_interval={**interval_estimator.to_dict(), "test_coverage_observed": coverage}, calibration=calibration)
    output = Path(output_root)
    model_path = output / "models" / f"{model_id}.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(json.dumps({"model_id": model_id, "task": REAL_SOLUBILITY_TASK, "dataset_id": dataset.dataset_id, "feature_schema_id": feature_schema.feature_schema_id, "intercept": intercept, "coefficients": coefficients.tolist(), "featurizer": {"schema_id": MorganFeaturizer.schema_id, "radius": featurizer.radius, "n_bits": featurizer.n_bits}, "applicability_domain": {"method": ad.method, "threshold": ad.threshold, "training_count": len(train)}, "uncertainty": interval_estimator.to_dict()}, indent=2, ensure_ascii=False), encoding="utf-8")
    metrics = dict(validation_report.metrics)
    artifact = ModelArtifactManifest.from_model_file(model_id=model_id, task=REAL_SOLUBILITY_TASK, training_run_id=training_run_id, dataset_id=dataset.dataset_id, dataset_hash=dataset.sha256, feature_schema_id=feature_schema.feature_schema_id, metrics=metrics, framework="numpy-ridge", framework_version=np.__version__, model_file=model_path, split_strategy=split_manifest.strategy, train_count=len(train), validation_count=len(validation_records), test_count=len(test), seed=seed, git_commit=git_commit, metadata={"target": dataset.target, "units": dataset.units, "uncertainty": interval_estimator.to_dict(), "applicability_domain": {"method": ad.method, "threshold": ad.threshold}, "external_test_status": "NOT_INDEPENDENT_EXTERNAL_DATA" if not external_test_acceptable else "ACCEPTED_BY_CALLER"})
    artifact_manifest_path = output / "models" / f"{model_id}.manifest.json"
    artifact.write(artifact_manifest_path)
    baseline_value = float(np.median(y_train))
    baseline_values = [baseline_value] * len(y_test)
    baseline_metrics = compute_regression_metrics(y_test.tolist(), baseline_values).to_dict()
    baseline_id = f"MODEL-{dataset.dataset_id.upper()}-REAL-BASELINE"
    baseline_run_id = f"TRN-{dataset.dataset_id.upper()}-REAL-BASELINE"
    baseline_path = output / "models" / f"{baseline_id}.json"
    baseline_path.write_text(json.dumps({"model_id": baseline_id, "task": REAL_SOLUBILITY_TASK, "dataset_id": dataset.dataset_id, "feature_schema_id": feature_schema.feature_schema_id, "estimator": "training_target_median", "value": baseline_value, "role": "real-data-incumbent-champion-baseline"}, indent=2, ensure_ascii=False), encoding="utf-8")
    champion = ModelArtifactManifest.from_model_file(model_id=baseline_id, task=REAL_SOLUBILITY_TASK, training_run_id=baseline_run_id, dataset_id=dataset.dataset_id, dataset_hash=dataset.sha256, feature_schema_id=feature_schema.feature_schema_id, metrics=baseline_metrics, framework="numpy-baseline", framework_version=np.__version__, model_file=baseline_path, split_strategy=split_manifest.strategy, train_count=len(train), validation_count=len(validation_records), test_count=len(test), seed=seed, git_commit=git_commit, metadata={"role": "real-data-incumbent-champion-baseline", "fit": "median of training targets", "target": dataset.target, "units": dataset.units})
    champion.write(output / "models" / f"{baseline_id}.manifest.json")
    training = TrainingRunManifest.create(training_run_id=training_run_id, model_id=model_id, task=REAL_SOLUBILITY_TASK, dataset_id=dataset.dataset_id, dataset_hash=dataset.sha256, feature_schema_id=feature_schema.feature_schema_id, split_strategy=split_manifest.strategy, train_count=len(train), validation_count=len(validation_records), test_count=len(test), seed=seed, hyperparameters={"estimator": "ridge_regression", "alpha": alpha, "features": "Morgan radius 2 / 2048 bits", "uncertainty": interval_estimator.method, "applicability_domain": ad.method}, metrics=metrics, framework="numpy-ridge", framework_version=np.__version__, git_commit=git_commit, environment_id=environment_id, model_artifact_hash=artifact.model_hash)
    training.write(output / "models" / f"{training_run_id}.manifest.json")
    split_manifest.write(output / "models" / "split-manifest.json")
    candidate = CandidateModel(manifest_id=training_run_id, model_manifest_id=model_id, training_run_id=training_run_id, stage="candidate")
    return RealMLResult(dataset, feature_schema, split_manifest, training, candidate, artifact, champion, model, validation_report, test_predictions, external_test_acceptable, ("The held-out scaffold split is not an independent external test source.", "R2 is reported as a regression score; it is not a confidence or reliability percentage.", "OUT_OF_DOMAIN predictions are excluded from normal ranking."))
