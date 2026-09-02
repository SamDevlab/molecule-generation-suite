from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

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
    code_commit: str | None = None
    model_file: str | None = None
    model_hash: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_model_file(cls, *, model_id: str, task: str, training_run_id: str, dataset_id: str, dataset_hash: str, feature_schema_id: str, metrics: dict[str, float], framework: str, model_file: str | Path, framework_version: str | None = None, code_commit: str | None = None, metadata: dict[str, Any] | None = None) -> "ModelArtifactManifest":
        path = Path(model_file)
        return cls(model_id=model_id, task=task, training_run_id=training_run_id, dataset_id=dataset_id, dataset_hash=dataset_hash, feature_schema_id=feature_schema_id, metrics=metrics, framework=framework, framework_version=framework_version, code_commit=code_commit, model_file=str(path), model_hash=sha256_file(path), metadata=metadata or {})

    @property
    def manifest_hash(self) -> str:
        return sha256_json(asdict(self))

    def write(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload["manifest_hash"] = self.manifest_hash
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return target
