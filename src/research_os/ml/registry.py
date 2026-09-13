"""In-memory and durable model registry contracts.

The durable registry stores manifests and content-addressed bytes. It never
loads or deserializes a model merely to verify provenance; verification is a
byte/hash and metadata operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping

from research_os.artifacts import ContentAddressedArtifactStore, ModelArtifactManifest
from research_os.core.hashing import sha256_json


class ModelRegistryError(ValueError):
    """A registry operation cannot be completed without violating provenance."""


class ModelVerificationError(ModelRegistryError):
    pass


def _identity_value(value: Any) -> Any:
    """Remove operational path fields recursively before hashing identities."""
    operational = {"path", "absolute_path", "registry_root", "manifest_path", "storage_path"}
    if isinstance(value, Mapping):
        return {key: _identity_value(item) for key, item in value.items() if key not in operational}
    if isinstance(value, (list, tuple)):
        return [_identity_value(item) for item in value]
    return value


class ModelStage(str, Enum):
    CANDIDATE = "candidate"
    CHAMPION = "champion"
    REJECTED = "rejected"
    RETIRED = "retired"


@dataclass(frozen=True)
class ModelVerification:
    model_id: str
    status: str
    first_loss: str | None
    gates: tuple[Mapping[str, Any], ...]
    scientific_model_id: str | None = None
    artifact_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "status": self.status,
            "first_loss": self.first_loss,
            "scientific_model_id": self.scientific_model_id,
            "artifact_sha256": self.artifact_sha256,
            "gates": [dict(gate) for gate in self.gates],
        }


@dataclass(frozen=True)
class ModelRecord:
    manifest: ModelArtifactManifest
    stage: str = ModelStage.CANDIDATE
    record_id: str | None = None
    lineage: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: str = "research-os.model-record.v1"

    def __post_init__(self) -> None:
        stage = self.stage.value if hasattr(self.stage, "value") else str(self.stage)
        if stage not in {ModelStage.CANDIDATE, ModelStage.CHAMPION, ModelStage.REJECTED, ModelStage.RETIRED}:
            raise ModelRegistryError(f"unsupported model stage: {stage}")
        object.__setattr__(self, "stage", stage)
        if self.record_id is None:
            object.__setattr__(self, "record_id", f"research-os.model-record.v1+{self.manifest.scientific_model_hash[:16]}")

    @property
    def model_id(self) -> str:
        return self.manifest.model_id

    @property
    def scientific_model_id(self) -> str:
        return self.manifest.scientific_model_id

    @property
    def artifact_sha256(self) -> str | None:
        return self.manifest.artifact_sha256

    def identity_payload(self) -> dict[str, Any]:
        """Record identity excludes timestamps, paths, and registry location."""
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "scientific_model_id": self.manifest.scientific_model_id,
            "scientific_identity": self.manifest.scientific_identity_payload(),
            "artifact_sha256": self.manifest.artifact_sha256,
            "artifact_size": self.manifest.artifact_size,
            "lineage": _identity_value(self.lineage),
            "provenance": _identity_value(self.provenance),
        }

    @property
    def record_hash(self) -> str:
        return sha256_json(self.identity_payload())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "record_hash": self.record_hash,
            "scientific_model_id": self.manifest.scientific_model_id,
            "artifact": {
                "artifact_id": self.manifest.artifact_id,
                "sha256": self.manifest.artifact_sha256,
                "size": self.manifest.artifact_size,
            },
            "stage": self.stage,
            "manifest": self.manifest.to_dict(),
            "lineage": dict(self.lineage),
            "provenance": dict(self.provenance),
            "registered_at": self.registered_at,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ModelRecord":
        if raw.get("schema_version") != "research-os.model-record.v1":
            raise ModelRegistryError("unsupported model record schema version")
        manifest_raw = raw.get("manifest")
        if not isinstance(manifest_raw, Mapping):
            raise ModelRegistryError("model record manifest is missing or invalid")
        record = cls(
            manifest=ModelArtifactManifest.from_mapping(manifest_raw),
            stage=str(raw.get("stage", ModelStage.CANDIDATE.value)),
            record_id=str(raw.get("record_id")) if raw.get("record_id") is not None else None,
            lineage=dict(raw.get("lineage") or {}),
            provenance=dict(raw.get("provenance") or {}),
            registered_at=str(raw.get("registered_at") or datetime.now(timezone.utc).isoformat()),
        )
        if raw.get("record_hash") != record.record_hash:
            raise ModelRegistryError(f"model record identity mismatch: {record.record_id}")
        if raw.get("scientific_model_id") != record.scientific_model_id:
            raise ModelRegistryError(f"scientific model identity mismatch: {record.record_id}")
        artifact = raw.get("artifact") or {}
        if artifact.get("sha256") != record.artifact_sha256 or artifact.get("size") != record.manifest.artifact_size:
            raise ModelRegistryError(f"model artifact identity mismatch: {record.record_id}")
        return record


class ModelRegistry:
    """Model registry with optional durable filesystem persistence.

    ``root=None`` preserves the legacy memory-only behavior. Supplying a root
    enables records/<record-id>.json and content-addressed artifacts under
    artifacts/. Durable registration requires a model file.
    """

    _SAFE_RECORD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:-]{0,255}$")

    def __init__(
        self,
        records: Iterable[ModelRecord] = (),
        *,
        root: str | Path | None = None,
        dataset_registry: Any | None = None,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else None
        self.dataset_registry = dataset_registry
        self._records: dict[str, ModelRecord] = {}
        self._records_by_id: dict[str, ModelRecord] = {}
        self.artifacts = ContentAddressedArtifactStore(self.root / "artifacts") if self.root is not None else None
        if self.root is not None:
            (self.root / "records").mkdir(parents=True, exist_ok=True)
            (self.root / "artifacts").mkdir(parents=True, exist_ok=True)
            for path in sorted((self.root / "records").glob("*.json")):
                self._load_persisted(path)
        for record in records:
            self.register(
                record.manifest,
                stage=record.stage,
                record_id=record.record_id,
                lineage=record.lineage,
                provenance=record.provenance,
            )

    def _load_persisted(self, path: Path) -> None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            record = ModelRecord.from_mapping(raw)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ModelRegistryError(f"cannot load model record {path}: {exc}") from exc
        self._index(record)

    def _index(self, record: ModelRecord) -> None:
        if record.record_id in self._records_by_id and self._records_by_id[record.record_id] != record:
            raise ModelRegistryError(f"duplicate model record id: {record.record_id}")
        if record.model_id in self._records and self._records[record.model_id] != record:
            raise ModelRegistryError(f"model_id already registered: {record.model_id}")
        self._records[record.model_id] = record
        self._records_by_id[str(record.record_id)] = record

    def _record_path(self, record_id: str) -> Path:
        if self.root is None:
            raise ModelRegistryError("durable registry root is not configured")
        if self._SAFE_RECORD_ID.fullmatch(record_id) is None:
            raise ModelRegistryError("unsafe model record id")
        return self.root / "records" / f"{record_id}.json"

    @staticmethod
    def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def register(
        self,
        manifest: ModelArtifactManifest,
        *,
        stage: ModelStage | str = ModelStage.CANDIDATE,
        record_id: str | None = None,
        lineage: Mapping[str, Any] | None = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> ModelRecord:
        stage_value = stage.value if hasattr(stage, "value") else str(stage)
        lineage_payload = dict(lineage or {})
        provenance_payload = dict(provenance or {})
        if manifest.implementation_identity:
            provenance_payload.setdefault("implementation_identity", manifest.implementation_identity)
        if manifest.environment_identity:
            provenance_payload.setdefault("environment_identity", manifest.environment_identity)

        if self.root is not None:
            if not manifest.model_file:
                raise ModelRegistryError("durable registration requires manifest.model_file")
            assert self.artifacts is not None
            artifact_ref = self.artifacts.put_artifact(manifest.model_file)
            if manifest.model_hash is not None and manifest.model_hash != artifact_ref.sha256:
                raise ModelRegistryError("MODEL_ARTIFACT_HASH_MISMATCH: manifest hash differs from bytes")
            if manifest.artifact_size is not None and manifest.artifact_size != artifact_ref.size:
                raise ModelRegistryError("MODEL_ARTIFACT_SIZE_MISMATCH: manifest size differs from bytes")
            manifest = replace(manifest, model_hash=artifact_ref.sha256, artifact_size=artifact_ref.size)
            provenance_payload["artifact"] = {
                **dict(provenance_payload.get("artifact") or {}),
                "sha256": artifact_ref.sha256,
                "size": artifact_ref.size,
                "storage": "content-addressed",
            }
            if self.dataset_registry is not None:
                try:
                    dataset = self.dataset_registry.get(manifest.dataset_id, manifest.dataset_version)
                except (KeyError, ValueError) as exc:
                    raise ModelRegistryError(f"DATASET_REFERENCE_MISSING: {manifest.dataset_id}") from exc
                if dataset.sha256 != manifest.dataset_hash:
                    raise ModelRegistryError("DATASET_IDENTITY_MISMATCH: dataset hash differs from manifest")
                verifier = getattr(self.dataset_registry, "verify", None)
                if callable(verifier):
                    dataset_verification = verifier(manifest.dataset_id, manifest.dataset_version)
                    if dataset_verification.status != "PASS":
                        raise ModelRegistryError(f"DATASET_PROVENANCE_INSUFFICIENT: {dataset_verification.first_loss}")
                provenance_payload["dataset"] = {
                    "id": dataset.dataset_id,
                    "version": dataset.version,
                    "sha256": dataset.sha256,
                    "schema_id": dataset.schema_id,
                    "scientific_dataset_id": getattr(dataset, "scientific_dataset_id", None),
                    "record_id": getattr(self.dataset_registry.get_record(manifest.dataset_id, manifest.dataset_version), "record_id", None) if hasattr(self.dataset_registry, "get_record") else None,
                }

        record = ModelRecord(
            manifest=manifest,
            stage=stage_value,
            record_id=record_id,
            lineage=lineage_payload,
            provenance=provenance_payload,
        )
        if self.root is not None:
            self._record_path(str(record.record_id))
        existing = self._records_by_id.get(str(record.record_id))
        if existing is not None:
            if existing.record_hash == record.record_hash and existing.artifact_sha256 == record.artifact_sha256:
                return existing
            raise ModelRegistryError(f"conflicting model registration: {record.record_id}")
        if manifest.model_id in self._records:
            raise ModelRegistryError(f"model_id already registered: {manifest.model_id}")
        self._index(record)
        if self.root is not None:
            self._atomic_write_json(self._record_path(str(record.record_id)), record.to_dict())
        return record

    def _resolve(self, model_id: str) -> ModelRecord:
        record = self._records.get(model_id) or self._records_by_id.get(model_id)
        if record is None:
            record = next((item for item in self._records_by_id.values() if item.scientific_model_id == model_id), None)
        if record is None:
            raise KeyError(f"model not registered: {model_id}")
        return record

    def get(self, model_id: str) -> ModelRecord:
        return self._resolve(model_id)

    def resolve(self, model_id: str) -> ModelRecord:
        """Resolve a record by legacy model id, record id, or scientific id."""
        return self.get(model_id)

    def list(self) -> tuple[ModelRecord, ...]:
        return tuple(sorted(self._records_by_id.values(), key=lambda item: str(item.record_id)))

    def inspect(self, model_id: str, *, verify: bool = True) -> dict[str, Any]:
        record = self.get(model_id)
        payload = record.to_dict()
        if verify:
            payload["verification"] = self.verify(model_id).to_dict()
        return payload

    def verify(self, model_id: str) -> ModelVerification:
        record = self.get(model_id)
        gates: list[dict[str, Any]] = []

        def gate(rule_id: str, status: str, reason: str) -> bool:
            gates.append({"rule_id": rule_id, "status": status, "reason": reason})
            return status == "PASS"

        if record.schema_version != "research-os.model-record.v1":
            return ModelVerification(str(record.record_id), "FAIL", "MODEL_RECORD_SCHEMA_UNSUPPORTED", tuple(gates))
        if self.root is not None:
            path = self._record_path(str(record.record_id))
            try:
                persisted = ModelRecord.from_mapping(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                gate("MODEL-RECORD-IDENTITY", "FAIL", f"record cannot be revalidated: {exc}")
                return ModelVerification(str(record.record_id), "FAIL", "MODEL_RECORD_HASH_MISMATCH", tuple(gates), record.scientific_model_id, record.artifact_sha256)
            if persisted.record_hash != record.record_hash or persisted.to_dict() != record.to_dict():
                gate("MODEL-RECORD-IDENTITY", "FAIL", "persisted record differs from loaded identity")
                return ModelVerification(str(record.record_id), "FAIL", "MODEL_RECORD_HASH_MISMATCH", tuple(gates), record.scientific_model_id, record.artifact_sha256)
        gate("MODEL-RECORD-IDENTITY", "PASS", "record identity is internally consistent")

        if self.root is None or self.artifacts is None:
            gate("MODEL-ARTIFACT-INTEGRITY", "INSUFFICIENT_EVIDENCE", "memory-only registry has no durable artifact boundary")
            return ModelVerification(str(record.record_id), "INSUFFICIENT_EVIDENCE", "MODEL_ARTIFACT_NOT_DURABLE", tuple(gates), record.scientific_model_id, record.artifact_sha256)

        artifact_hash = record.artifact_sha256
        if not artifact_hash:
            gate("MODEL-ARTIFACT-EXISTS", "FAIL", "artifact hash is missing")
            return ModelVerification(str(record.record_id), "FAIL", "MODEL_ARTIFACT_MISSING", tuple(gates), record.scientific_model_id, None)
        artifact_path = self.root / "artifacts" / "sha256" / artifact_hash[:2] / artifact_hash
        if not artifact_path.is_file():
            gate("MODEL-ARTIFACT-EXISTS", "FAIL", "content-addressed artifact is unavailable")
            return ModelVerification(str(record.record_id), "FAIL", "MODEL_ARTIFACT_MISSING", tuple(gates), record.scientific_model_id, artifact_hash)
        if not self.artifacts.verify_artifact(artifact_hash):
            gate("MODEL-ARTIFACT-INTEGRITY", "FAIL", "content-addressed bytes do not match SHA-256")
            return ModelVerification(str(record.record_id), "FAIL", "MODEL_ARTIFACT_HASH_MISMATCH", tuple(gates), record.scientific_model_id, artifact_hash)
        gate("MODEL-ARTIFACT-INTEGRITY", "PASS", "artifact bytes and SHA-256 match")
        if record.manifest.artifact_size is not None and artifact_path.stat().st_size != record.manifest.artifact_size:
            gate("MODEL-ARTIFACT-SIZE", "FAIL", "artifact byte size differs")
            return ModelVerification(str(record.record_id), "FAIL", "MODEL_ARTIFACT_SIZE_MISMATCH", tuple(gates), record.scientific_model_id, artifact_hash)
        gate("MODEL-ARTIFACT-SIZE", "PASS", "artifact byte size matches")

        if record.scientific_model_id != record.manifest.scientific_model_id:
            gate("MODEL-SCIENTIFIC-IDENTITY", "FAIL", "scientific model identity does not reproduce")
            return ModelVerification(str(record.record_id), "FAIL", "MODEL_SCIENTIFIC_IDENTITY_MISMATCH", tuple(gates), record.scientific_model_id, artifact_hash)
        gate("MODEL-SCIENTIFIC-IDENTITY", "PASS", "scientific model identity reproduces from canonical fields")

        dataset = record.provenance.get("dataset", {})
        if self.dataset_registry is not None:
            try:
                current = self.dataset_registry.get(record.manifest.dataset_id, record.manifest.dataset_version)
            except KeyError:
                gate("MODEL-DATASET-PROVENANCE", "FAIL", "declared dataset is unavailable")
                return ModelVerification(str(record.record_id), "FAIL", "DATASET_REFERENCE_MISSING", tuple(gates), record.scientific_model_id, artifact_hash)
            if current.sha256 != record.manifest.dataset_hash:
                gate("MODEL-DATASET-PROVENANCE", "FAIL", "dataset SHA-256 differs from registered model")
                return ModelVerification(str(record.record_id), "FAIL", "DATASET_IDENTITY_MISMATCH", tuple(gates), record.scientific_model_id, artifact_hash)
            verifier = getattr(self.dataset_registry, "verify", None)
            if callable(verifier):
                dataset_verification = verifier(record.manifest.dataset_id, record.manifest.dataset_version)
                if dataset_verification.status != "PASS":
                    gate("MODEL-DATASET-PROVENANCE", dataset_verification.status, f"dataset registry verification failed: {dataset_verification.first_loss}")
                    return ModelVerification(str(record.record_id), dataset_verification.status, dataset_verification.first_loss or "DATASET_PROVENANCE_INSUFFICIENT", tuple(gates), record.scientific_model_id, artifact_hash)
        elif dataset and dataset.get("sha256") != record.manifest.dataset_hash:
            gate("MODEL-DATASET-PROVENANCE", "FAIL", "recorded dataset reference differs from manifest")
            return ModelVerification(str(record.record_id), "FAIL", "DATASET_IDENTITY_MISMATCH", tuple(gates), record.scientific_model_id, artifact_hash)
        gate("MODEL-DATASET-PROVENANCE", "PASS", "dataset identity is recorded and consistent")

        if record.manifest.implementation_identity:
            implementation = record.provenance.get("implementation_identity")
            if implementation != record.manifest.implementation_identity:
                gate("MODEL-IMPLEMENTATION-PROVENANCE", "FAIL", "implementation identity differs")
                return ModelVerification(str(record.record_id), "FAIL", "IMPLEMENTATION_IDENTITY_MISMATCH", tuple(gates), record.scientific_model_id, artifact_hash)
        gate("MODEL-IMPLEMENTATION-PROVENANCE", "PASS", "implementation identity is consistent or legacy-unspecified")

        source = record.provenance.get("source_run", {})
        source_path = source.get("manifest_path") if isinstance(source, Mapping) else None
        if source_path:
            source_file = Path(str(source_path))
            if not source_file.is_file():
                gate("MODEL-SOURCE-RUN", "FAIL", "source run manifest is unavailable")
                return ModelVerification(str(record.record_id), "FAIL", "SOURCE_RUN_MISSING", tuple(gates), record.scientific_model_id, artifact_hash)
            try:
                source_raw = json.loads(source_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                gate("MODEL-SOURCE-RUN", "FAIL", "source run manifest is unreadable")
                return ModelVerification(str(record.record_id), "FAIL", "SOURCE_RUN_INVALID", tuple(gates), record.scientific_model_id, artifact_hash)
            if source.get("run_id") and source_raw.get("experiment_id") != source.get("run_id"):
                gate("MODEL-SOURCE-RUN", "FAIL", "source run identity differs")
                return ModelVerification(str(record.record_id), "FAIL", "SOURCE_RUN_IDENTITY_MISMATCH", tuple(gates), record.scientific_model_id, artifact_hash)
        gate("MODEL-SOURCE-RUN", "PASS", "source training run reference is consistent or legacy-unspecified")
        gate("MODEL-LINEAGE", "PASS", "dataset and training lineage are preserved")
        return ModelVerification(str(record.record_id), "PASS", None, tuple(gates), record.scientific_model_id, artifact_hash)

    def champion(self, task: str | None = None) -> ModelRecord | None:
        champions = [record for record in self.list() if record.stage == ModelStage.CHAMPION and (task is None or record.manifest.task == task)]
        if len(champions) > 1:
            raise ValueError(f"multiple champion models registered for task: {task or '*'}")
        return champions[0] if champions else None

    def candidates(self, task: str | None = None) -> tuple[ModelRecord, ...]:
        return tuple(record for record in self.list() if record.stage == ModelStage.CANDIDATE and (task is None or record.manifest.task == task))

    def set_stage(self, model_id: str, stage: ModelStage | str) -> ModelRecord:
        current = self.get(model_id)
        updated = replace(current, stage=stage.value if hasattr(stage, "value") else str(stage))
        self._records[updated.model_id] = updated
        self._records_by_id[str(updated.record_id)] = updated
        if self.root is not None:
            self._atomic_write_json(self._record_path(str(updated.record_id)), updated.to_dict())
        return updated

    def promote(self, model_id: str, *, task: str | None = None) -> ModelRecord:
        candidate = self.get(model_id)
        if candidate.stage != ModelStage.CANDIDATE:
            raise ValueError("only candidate models can be promoted")
        old = self.champion(task or candidate.manifest.task)
        if old and old.model_id != model_id:
            self.set_stage(old.model_id, ModelStage.RETIRED)
        return self.set_stage(model_id, ModelStage.CHAMPION)
