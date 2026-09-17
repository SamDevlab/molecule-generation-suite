from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Mapping
import json
import uuid

from research_os.core.hashing import sha256_json
from research_os.ml.schema import SplitStrategy


@dataclass(frozen=True)
class FeatureSchema:
    feature_schema_id: str
    features: tuple[str, ...]
    description: str = ""
    version: str = "1"

    def __post_init__(self) -> None:
        raw_features = (self.features,) if isinstance(self.features, str) else self.features
        object.__setattr__(self, "features", tuple(str(feature) for feature in raw_features))
        if not self.feature_schema_id.strip() or not self.features:
            raise ValueError("feature schema requires an id and at least one feature")

    def to_dict(self) -> dict[str, Any]:
        return {"feature_schema_id": self.feature_schema_id, "features": list(self.features), "description": self.description, "version": self.version}


@dataclass(frozen=True)
class TrainingRunManifest:
    training_run_id: str
    model_id: str
    task: str
    dataset_id: str
    dataset_hash: str
    feature_schema_id: str
    split_strategy: SplitStrategy | str
    train_count: int
    validation_count: int
    test_count: int
    seed: int
    hyperparameters: dict[str, Any]
    metrics: dict[str, float]
    framework: str
    framework_version: str | None
    git_commit: str | None
    environment_id: str | None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model_artifact_hash: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "split_strategy", self.split_strategy.value if isinstance(self.split_strategy, SplitStrategy) else str(self.split_strategy))
        if min(self.train_count, self.validation_count, self.test_count) < 0:
            raise ValueError("training split counts cannot be negative")
        if not self.hyperparameters:
            raise ValueError("training hyperparameters must be recorded explicitly")
        if any(not math.isfinite(float(value)) for value in self.metrics.values()):
            raise ValueError("training metrics must be finite numeric values")

    @classmethod
    def create(cls, **kwargs: Any) -> "TrainingRunManifest":
        return cls(training_run_id=kwargs.pop("training_run_id", f"TRN-{uuid.uuid4().hex[:12].upper()}"), **kwargs)

    @property
    def manifest_hash(self) -> str:
        return sha256_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["split_strategy"] = str(self.split_strategy)
        return data

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "TrainingRunManifest":
        values = dict(raw)
        values.pop("manifest_hash", None)
        return cls(**values)

    def write(self, path: str) -> str:
        from pathlib import Path
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_dict()
        payload["manifest_hash"] = self.manifest_hash
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(target)


@dataclass(frozen=True)
class CandidateModel:
    manifest_id: str
    model_manifest_id: str
    training_run_id: str
    stage: str = "candidate"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)
