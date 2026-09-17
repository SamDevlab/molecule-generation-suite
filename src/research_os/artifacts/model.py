from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
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
    # Explicit provenance fields are optional so legacy in-memory manifests
    # remain readable.  They are intentionally separate from operational
    # metadata and from the serialized artifact bytes.
    model_family: str | None = None
    model_adapter: str | None = None
    adapter_version: str | None = None
    preprocessing_identity: str | None = None
    target: str | None = None
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    dataset_version: str | None = None
    implementation_identity: str | None = None
    environment_identity: str | None = None
    artifact_size: int | None = None

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
        if self.artifact_size is not None and self.artifact_size < 0:
            raise ValueError("artifact_size cannot be negative")

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
        model_family: str | None = None,
        model_adapter: str | None = None,
        adapter_version: str | None = None,
        preprocessing_identity: str | None = None,
        target: str | None = None,
        hyperparameters: dict[str, Any] | None = None,
        dataset_version: str | None = None,
        implementation_identity: str | None = None,
        environment_identity: str | None = None,
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
            model_family=model_family,
            model_adapter=model_adapter,
            adapter_version=adapter_version,
            preprocessing_identity=preprocessing_identity,
            target=target,
            hyperparameters=hyperparameters or {},
            dataset_version=dataset_version,
            implementation_identity=implementation_identity,
            environment_identity=environment_identity,
            artifact_size=path.stat().st_size,
        )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ModelArtifactManifest":
        values = dict(raw)
        values.pop("manifest_hash", None)
        # Older manifests may contain the registry-facing aliases.  The
        # canonical manifest keeps model_hash as the byte identity.
        artifact_sha256 = values.pop("artifact_sha256", None)
        if artifact_sha256 and not values.get("model_hash"):
            values["model_hash"] = artifact_sha256
        values.pop("scientific_model_id", None)
        values.pop("scientific_model_hash", None)
        values.pop("artifact_id", None)
        return cls(**values)

    @property
    def artifact_sha256(self) -> str | None:
        return self.model_hash

    @property
    def artifact_id(self) -> str | None:
        return f"research-os.model.artifact.v1+{self.model_hash}" if self.model_hash else None

    def scientific_identity_payload(self) -> dict[str, Any]:
        """Return protocol/training identity, excluding bytes and operations."""
        return {
            "schema": "research-os.model-scientific.v1",
            "task": self.task,
            "model_family": self.model_family or self.framework,
            "model_adapter": self.model_adapter or self.framework,
            "adapter_version": self.adapter_version or self.framework_version,
            "dataset": {
                "id": self.dataset_id,
                "version": self.dataset_version,
                "sha256": self.dataset_hash,
            },
            "feature_schema_id": self.feature_schema_id,
            "target": self.target or self.metadata.get("target"),
            "preprocessing_identity": self.preprocessing_identity,
            "split": {
                "strategy": self.split_strategy,
                "train_count": self.train_count,
                "validation_count": self.validation_count,
                "test_count": self.test_count,
            },
            "seed": self.seed,
            "hyperparameters": dict(self.hyperparameters),
            "metrics": dict(self.metrics),
        }

    @property
    def scientific_model_hash(self) -> str:
        return sha256_json(self.scientific_identity_payload())

    @property
    def scientific_model_id(self) -> str:
        return f"research-os.model.scientific.v1+{self.scientific_model_hash[:16]}"

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
