from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import math

from research_os.core.hashing import sha256_file, sha256_json


@dataclass(frozen=True)
class ModelArtifactManifest:
    """Immutable provenance record for a trained statistical model."""

    model_id: str
    task: str
    training_run_id: str
    dataset_id: str
    dataset_hash: str
    feature_schema_id: str
    metrics: dict[str, float]
    framework: str
    framework_version: str | None = None
    split_strategy: str = "unspecified"
    train_count: int = 0
    validation_count: int = 0
    test_count: int = 0
    seed: int | None = None
    git_commit: str | None = None
    # Kept as a compatibility alias for manifests produced before v1.3.
    code_commit: str | None = None
    model_file: str | None = None
    model_hash: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if hasattr(self.split_strategy, "value"):
            object.__setattr__(self, "split_strategy", self.split_strategy.value)
        if not self.model_id.strip() or not self.task.strip() or not self.framework.strip():
            raise ValueError("model_id, task and framework are required")
        if any(not math.isfinite(float(value)) for value in self.metrics.values()):
            raise ValueError("model metrics must be finite numeric values")
        if self.git_commit is None and self.code_commit is not None:
            object.__setattr__(self, "git_commit", self.code_commit)
        elif self.code_commit is None and self.git_commit is not None:
            object.__setattr__(self, "code_commit", self.git_commit)
        for name in ("train_count", "validation_count", "test_count"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")

    @classmethod
    def from_model_file(
        cls,
        *,
        model_id: str,
        task: str,
        training_run_id: str,
        dataset_id: str,
        dataset_hash: str,
        feature_schema_id: str,
        metrics: dict[str, float],
        framework: str,
        model_file: str | Path,
        framework_version: str | None = None,
        split_strategy: str = "unspecified",
        train_count: int = 0,
        validation_count: int = 0,
        test_count: int = 0,
        seed: int | None = None,
        git_commit: str | None = None,
        code_commit: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ModelArtifactManifest":
        path = Path(model_file)
        return cls(
            model_id=model_id,
            task=task,
            training_run_id=training_run_id,
            dataset_id=dataset_id,
            dataset_hash=dataset_hash,
            feature_schema_id=feature_schema_id,
            metrics=metrics,
            framework=framework,
            framework_version=framework_version,
            split_strategy=split_strategy,
            train_count=train_count,
            validation_count=validation_count,
            test_count=test_count,
            seed=seed,
            git_commit=git_commit,
            code_commit=code_commit,
            model_file=str(path),
            model_hash=sha256_file(path),
            metadata=metadata or {},
        )

    @property
    def manifest_hash(self) -> str:
        return sha256_json(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_dict()
        payload["manifest_hash"] = self.manifest_hash
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return target
