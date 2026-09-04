from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from research_os.artifacts import ModelArtifactManifest


class ModelStage(str, Enum):
    CANDIDATE = "candidate"
    CHAMPION = "champion"
    REJECTED = "rejected"
    RETIRED = "retired"


@dataclass(frozen=True)
class ModelRecord:
    manifest: ModelArtifactManifest
    stage: ModelStage

    @property
    def model_id(self) -> str:
        return self.manifest.model_id


class ModelRegistry:
    """Small deterministic registry boundary; persistence can be added later."""

    def __init__(self, records: Iterable[ModelRecord] = ()):
        self._records: dict[str, ModelRecord] = {}
        for record in records:
            self.register(record.manifest, stage=record.stage)

    def register(self, manifest: ModelArtifactManifest, *, stage: ModelStage = ModelStage.CANDIDATE) -> ModelRecord:
        if manifest.model_id in self._records:
            raise ValueError(f"model_id already registered: {manifest.model_id}")
        record = ModelRecord(manifest, stage if isinstance(stage, ModelStage) else ModelStage(str(stage)))
        self._records[manifest.model_id] = record
        return record

    def get(self, model_id: str) -> ModelRecord:
        try:
            return self._records[model_id]
        except KeyError as exc:
            raise KeyError(f"model not registered: {model_id}") from exc

    def champion(self, task: str | None = None) -> ModelRecord | None:
        champions = [record for record in self._records.values() if record.stage == ModelStage.CHAMPION and (task is None or record.manifest.task == task)]
        if len(champions) > 1:
            raise ValueError(f"multiple champion models registered for task: {task or '*'}")
        return champions[0] if champions else None

    def candidates(self, task: str | None = None) -> tuple[ModelRecord, ...]:
        return tuple(record for record in self._records.values() if record.stage == ModelStage.CANDIDATE and (task is None or record.manifest.task == task))

    def set_stage(self, model_id: str, stage: ModelStage) -> ModelRecord:
        current = self.get(model_id)
        updated = ModelRecord(current.manifest, stage)
        self._records[model_id] = updated
        return updated

    def promote(self, model_id: str, *, task: str | None = None) -> ModelRecord:
        candidate = self.get(model_id)
        if candidate.stage != ModelStage.CANDIDATE:
            raise ValueError("only candidate models can be promoted")
        old = self.champion(task or candidate.manifest.task)
        if old and old.model_id != model_id:
            self.set_stage(old.model_id, ModelStage.RETIRED)
        return self.set_stage(model_id, ModelStage.CHAMPION)
