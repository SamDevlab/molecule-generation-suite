from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from research_os.artifacts import ContentAddressedArtifactStore
from research_os.core.hashing import canonical_json, sha256_file, sha256_json
from research_os.core.types import EvidenceLevel
from research_os.datasets.schema import DatasetManifest, DatasetSourceType


class DatasetRegistryError(ValueError):
    pass


class StorageUnavailableError(RuntimeError):
    pass


class DatasetSchemaError(DatasetRegistryError):
    pass


@dataclass(frozen=True)
class DatasetInspection:
    path: str
    format: str
    sha256: str
    row_count: int
    column_count: int
    columns: tuple[str, ...]
    schema: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "format": self.format, "sha256": self.sha256, "row_count": self.row_count, "column_count": self.column_count, "columns": list(self.columns), "schema": dict(self.schema)}


class ParquetStore(Protocol):
    def write(self, records: Iterable[Mapping[str, Any]], path: str | Path) -> Path: ...
    def read(self, path: str | Path) -> list[dict[str, Any]]: ...


class DuckDBQuery(Protocol):
    def query(self, path: str | Path, sql: str) -> list[dict[str, Any]]: ...


class ParquetDatasetStore:
    """Optional Parquet implementation; missing engines fail explicitly."""

    def write(self, records: Iterable[Mapping[str, Any]], path: str | Path) -> Path:
        try:
            import pyarrow as pa  # type: ignore[import-not-found]
            import pyarrow.parquet as parquet  # type: ignore[import-not-found]
        except ImportError as exc:
            raise StorageUnavailableError("Parquet support requires pyarrow; no dataset was written") from exc
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        parquet.write_table(pa.Table.from_pylist([dict(record) for record in records]), target)
        return target

    def read(self, path: str | Path) -> list[dict[str, Any]]:
        try:
            import pyarrow.parquet as parquet  # type: ignore[import-not-found]
        except ImportError as exc:
            raise StorageUnavailableError("Parquet support requires pyarrow; no dataset was read") from exc
        return parquet.read_table(path).to_pylist()


def inspect_dataset(path: str | Path) -> DatasetInspection:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    suffix = source.suffix.lower()
    if suffix == ".csv":
        return _inspect_csv(source)
    if suffix == ".parquet":
        return _inspect_parquet(source)
    raise DatasetRegistryError(f"unsupported dataset format: {source.suffix}")


def _inspect_csv(source: Path) -> DatasetInspection:
    with source.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = tuple(reader.fieldnames or ())
        if not columns or any(not column for column in columns) or len(set(columns)) != len(columns):
            raise DatasetSchemaError("CSV must have a non-empty header")
        row_count = 0
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise DatasetSchemaError("CSV row does not match its header schema")
            row_count += 1
    return DatasetInspection(str(source), "csv", sha256_file(source), row_count, len(columns), columns, {column: "string" for column in columns})


def _inspect_parquet(source: Path) -> DatasetInspection:
    try:
        import pyarrow.parquet as parquet  # type: ignore[import-not-found]
    except ImportError as exc:
        raise StorageUnavailableError("Parquet inspection requires pyarrow") from exc
    parquet_file = parquet.ParquetFile(source)
    schema = parquet_file.schema_arrow
    return DatasetInspection(str(source), "parquet", sha256_file(source), parquet_file.metadata.num_rows, len(schema.names), tuple(schema.names), {field.name: str(field.type) for field in schema})


def convert_csv_to_parquet(
    csv_path: str | Path,
    parquet_path: str | Path,
    *,
    dataset_id: str,
    version: str,
    schema_id: str,
    transformation_run_id: str | None = None,
    **metadata: Any,
) -> DatasetManifest:
    """Stream a CSV into Parquet and persist a manifest for the output artifact."""
    source = Path(csv_path)
    target = Path(parquet_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    _inspect_csv(source)
    try:
        import pyarrow.csv as arrow_csv  # type: ignore[import-not-found]
        import pyarrow.parquet as parquet  # type: ignore[import-not-found]
    except ImportError as exc:
        raise StorageUnavailableError("CSV to Parquet conversion requires pyarrow") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    reader = arrow_csv.open_csv(source)
    try:
        first_batch = reader.read_next_batch()
    except StopIteration as exc:
        raise DatasetSchemaError("CSV must contain a header and at least one data row") from exc
    if first_batch.num_rows == 0:
        raise DatasetSchemaError("CSV must contain at least one data row")
    writer = parquet.ParquetWriter(target, first_batch.schema, compression="zstd")
    row_count = 0
    try:
        writer.write_batch(first_batch)
        row_count += first_batch.num_rows
        while True:
            try:
                batch = reader.read_next_batch()
            except StopIteration:
                break
            if batch.schema != first_batch.schema:
                raise DatasetSchemaError("CSV batches produced inconsistent Arrow schemas")
            writer.write_batch(batch)
            row_count += batch.num_rows
    finally:
        writer.close()
    output = inspect_dataset(target)
    return DatasetManifest(
        dataset_id,
        version,
        schema_id,
        output.sha256,
        row_count,
        column_count=output.column_count,
        **_manifest_kwargs({
            **metadata,
            "storage_format": "parquet",
            "source_file_hash": metadata.get("source_file_hash") or sha256_file(source),
            "artifact_path": target,
            "source_path": source,
            "transformation_run_id": transformation_run_id,
        }),
    )


class DuckDBDatasetQuery:
    """Optional read/query boundary for Parquet datasets."""

    def query(self, path: str | Path, sql: str) -> list[dict[str, Any]]:
        try:
            import duckdb  # type: ignore[import-not-found]
        except ImportError as exc:
            raise StorageUnavailableError("DuckDB support is optional and is not installed") from exc
        connection = duckdb.connect()
        try:
            result = connection.execute(sql, [str(path)]) if "?" in sql else connection.execute(sql)
            columns = [item[0] for item in result.description]
            return [dict(zip(columns, row)) for row in result.fetchall()]
        finally:
            connection.close()


def _records_hash(records: Iterable[Mapping[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    materialized = [dict(record) for record in records]
    if materialized:
        expected = set(materialized[0])
        if any(set(record) != expected for record in materialized[1:]):
            raise DatasetSchemaError("records have inconsistent column schemas")
    return sha256_json(materialized), materialized


def _manifest_kwargs(kwargs: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sources": tuple(kwargs.get("sources") or ()),
        "licenses": tuple(kwargs.get("licenses") or ()),
        "source_types": tuple(kwargs.get("source_types") or ()),
        "evidence_levels": tuple(kwargs.get("evidence_levels") or ()),
        "synthetic_fraction": float(kwargs.get("synthetic_fraction", 0.0)),
        "experimental_fraction": float(kwargs.get("experimental_fraction", 0.0)),
        "computational_fraction": float(kwargs.get("computational_fraction", 0.0)),
        "parent_datasets": tuple(kwargs.get("parent_datasets") or ()),
        "transformation_run_id": kwargs.get("transformation_run_id"),
        "notes": kwargs.get("notes"),
        "storage_format": str(kwargs.get("storage_format", "records")),
        "source_file_hash": kwargs.get("source_file_hash"),
        "artifact_path": str(kwargs["artifact_path"]) if kwargs.get("artifact_path") is not None else None,
        "source_path": str(kwargs["source_path"]) if kwargs.get("source_path") is not None else None,
        "target": kwargs.get("target"),
        "units": kwargs.get("units"),
        "conditions": dict(kwargs.get("conditions") or {}),
        "measurement_method": kwargs.get("measurement_method"),
        "uncertainty": kwargs.get("uncertainty"),
        "source_url": kwargs.get("source_url"),
        "redistribution_status": kwargs.get("redistribution_status"),
        "provenance": tuple(kwargs.get("provenance") or ()),
        "license": kwargs.get("license"),
        "artifact_size": int(kwargs["artifact_size"]) if kwargs.get("artifact_size") is not None else None,
        "implementation_identity": kwargs.get("implementation_identity"),
        "environment_identity": kwargs.get("environment_identity"),
    }


def _identity_value(value: Any) -> Any:
    """Remove operational paths and timestamps from record identity."""
    operational = {"path", "absolute_path", "registry_root", "manifest_path", "storage_path", "source_path", "artifact_path", "registered_at", "created_at", "updated_at", "hostname"}
    if isinstance(value, Mapping):
        return {key: _identity_value(item) for key, item in value.items() if key not in operational}
    if isinstance(value, (list, tuple)):
        return [_identity_value(item) for item in value]
    return value


@dataclass(frozen=True)
class DatasetRecord:
    """Durable record envelope; the manifest remains readable independently."""

    manifest: DatasetManifest
    record_id: str | None = None
    lineage: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    registered_at: str = ""
    schema_version: str = "research-os.dataset-record.v1"
    legacy: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "lineage", dict(self.lineage or {}))
        object.__setattr__(self, "provenance", dict(self.provenance or {}))
        if not self.registered_at:
            object.__setattr__(self, "registered_at", datetime.now(timezone.utc).isoformat())
        if self.schema_version != "research-os.dataset-record.v1" and not self.legacy:
            raise DatasetRegistryError("unsupported dataset record schema version")
        if self.record_id is None and not self.legacy:
            object.__setattr__(self, "record_id", f"research-os.dataset-record.v1+{sha256_json(self._base_identity())[:16]}")

    @property
    def scientific_dataset_id(self) -> str:
        return self.manifest.scientific_dataset_id

    @property
    def artifact_sha256(self) -> str:
        return self.manifest.sha256.lower()

    def _base_identity(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scientific_dataset_id": self.manifest.scientific_dataset_id,
            "scientific_identity": self.manifest.scientific_identity_payload(),
            "artifact_sha256": self.artifact_sha256,
            "artifact_size": self.manifest.artifact_size,
            "lineage": _identity_value(self.lineage),
            "provenance": _identity_value(self.provenance),
        }

    @property
    def record_hash(self) -> str:
        if self.record_id is None:
            return ""
        return sha256_json({**self._base_identity(), "record_id": self.record_id})

    def to_dict(self) -> dict[str, Any]:
        if self.legacy:
            return self.manifest.to_dict()
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "record_hash": self.record_hash,
            "scientific_dataset_id": self.scientific_dataset_id,
            "artifact": {"artifact_id": self.manifest.artifact_id, "sha256": self.artifact_sha256, "size": self.manifest.artifact_size},
            "manifest": self.manifest.to_dict(),
            "lineage": dict(self.lineage),
            "provenance": dict(self.provenance),
            "registered_at": self.registered_at,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "DatasetRecord":
        if raw.get("schema_version") != "research-os.dataset-record.v1":
            raise DatasetRegistryError("unsupported dataset record schema version")
        manifest_raw = raw.get("manifest")
        if not isinstance(manifest_raw, Mapping):
            raise DatasetRegistryError("dataset record manifest is missing or invalid")
        record = cls(
            DatasetManifest.from_mapping(manifest_raw),
            record_id=str(raw.get("record_id")) if raw.get("record_id") is not None else None,
            lineage=dict(raw.get("lineage") or {}),
            provenance=dict(raw.get("provenance") or {}),
            registered_at=str(raw.get("registered_at") or ""),
        )
        if not record.record_id or raw.get("record_hash") != record.record_hash:
            raise DatasetRegistryError(f"dataset record identity mismatch: {record.record_id}")
        if raw.get("scientific_dataset_id") != record.scientific_dataset_id:
            raise DatasetRegistryError(f"scientific dataset identity mismatch: {record.record_id}")
        artifact = raw.get("artifact") or {}
        if artifact.get("sha256") != record.artifact_sha256 or artifact.get("size") != record.manifest.artifact_size:
            raise DatasetRegistryError(f"dataset artifact identity mismatch: {record.record_id}")
        return record


@dataclass(frozen=True)
class DatasetVerification:
    dataset_id: str
    version: str
    status: str
    first_loss: str | None
    gates: tuple[Mapping[str, Any], ...]
    scientific_dataset_id: str | None = None
    artifact_sha256: str | None = None
    record_id: str | None = None
    legacy: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "status": self.status,
            "first_loss": self.first_loss,
            "scientific_dataset_id": self.scientific_dataset_id,
            "artifact_sha256": self.artifact_sha256,
            "record_id": self.record_id,
            "legacy": self.legacy,
            "gates": [dict(gate) for gate in self.gates],
        }


class DatasetRegistry:
    """Versioned dataset registry with atomic records and durable bytes.

    ``root=None`` preserves the legacy memory-only API.  A configured root
    stores records in ``manifests/`` and managed bytes in a content-addressed
    ``artifacts/`` tree.  External references are explicit and never copied.
    """

    _SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

    def __init__(self, manifests: Iterable[DatasetManifest] = (), *, root: str | Path | None = None):
        self._manifests: dict[tuple[str, str], DatasetManifest] = {}
        self._records: dict[tuple[str, str], DatasetRecord] = {}
        self._record_paths: dict[tuple[str, str], Path] = {}
        self.root = Path(root).resolve() if root is not None else None
        self.artifacts = ContentAddressedArtifactStore(self.root / "artifacts") if self.root is not None else None
        if self.root is not None:
            for directory in ("manifests", "artifacts", "raw", "curated", "external", "synthetic"):
                (self.root / directory).mkdir(parents=True, exist_ok=True)
            for path in sorted((self.root / "manifests").glob("*.manifest.json")):
                self._load_persisted(path)
        for manifest in manifests:
            self.register(manifest)

    def _load_persisted(self, path: Path) -> None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, Mapping) and raw.get("schema_version") == "research-os.dataset-record.v1":
                record = DatasetRecord.from_mapping(raw)
            else:
                if isinstance(raw, Mapping) and raw.get("schema_version") is not None:
                    raise DatasetRegistryError("unsupported dataset record schema version")
                # Historical flat manifests remain readable but are explicitly
                # marked legacy rather than receiving an invented record ID.
                record = DatasetRecord(DatasetManifest.from_mapping(raw), legacy=True)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise DatasetRegistryError(f"cannot load dataset record {path}: {exc}") from exc
        key = (record.manifest.dataset_id, record.manifest.version)
        if key in self._records and self._records[key] != record:
            raise DatasetRegistryError(f"duplicate dataset record: {key[0]}@{key[1]}")
        self._records[key] = record
        self._manifests[key] = record.manifest
        self._record_paths[key] = path

    @classmethod
    def _validate_reference(cls, dataset_id: str, version: str) -> None:
        if cls._SAFE_REF.fullmatch(dataset_id) is None or cls._SAFE_REF.fullmatch(version) is None:
            raise DatasetRegistryError("dataset_id and version must be safe registry references")

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

    def _record_path(self, record_id: str) -> Path:
        if self.root is None:
            raise DatasetRegistryError("durable registry root is not configured")
        if not record_id.startswith("research-os.dataset-record.v1+") or self._SAFE_REF.fullmatch(record_id.replace("research-os.dataset-record.v1+", "", 1)) is None:
            raise DatasetRegistryError("unsafe dataset record id")
        return self.root / "manifests" / f"{record_id}.manifest.json"

    def _parent_key(self, reference: str) -> tuple[str, str] | None:
        if "@" in reference:
            dataset_id, version = reference.rsplit("@", 1)
            return dataset_id, version
        matches = [key for key in self._manifests if key[0] == reference]
        return matches[-1] if len(matches) == 1 else None

    def _validate_lineage(self, manifest: DatasetManifest) -> None:
        for reference in manifest.parent_datasets:
            key = self._parent_key(reference)
            if key is None or key not in self._manifests:
                raise DatasetRegistryError(f"DATASET_PARENT_MISSING: {reference}")
            seen: set[tuple[str, str]] = set()
            current = key
            while current in self._manifests:
                if current in seen or current == (manifest.dataset_id, manifest.version):
                    raise DatasetRegistryError("DATASET_LINEAGE_CYCLE")
                seen.add(current)
                parent = self._manifests[current].parent_datasets
                current = self._parent_key(parent[0]) if parent else ("", "")

    def _normalise_artifact(self, manifest: DatasetManifest, *, artifact_mode: str | None) -> tuple[DatasetManifest, dict[str, Any]]:
        if self.root is None:
            return manifest, {"artifact_mode": artifact_mode or "memory"}
        if artifact_mode not in {None, "managed", "external"}:
            raise DatasetRegistryError("artifact_mode must be managed or external")
        source = Path(manifest.artifact_path) if manifest.artifact_path else None
        restricted = (manifest.redistribution_status or "").lower() in {"restricted", "prohibited", "no-redistribution", "not-redistributable"}
        mode = artifact_mode or ("external" if manifest.storage_format == "external-reference" else "managed")
        if restricted and mode == "managed":
            raise DatasetRegistryError("DATASET_ARTIFACT_RESTRICTED: explicit external mode is required")
        if source is None:
            raise DatasetRegistryError("durable registration requires manifest.artifact_path")
        if not source.is_file():
            raise FileNotFoundError(source)
        digest = sha256_file(source)
        if digest != manifest.sha256.lower():
            raise DatasetRegistryError("DATASET_ARTIFACT_HASH_MISMATCH: manifest hash differs from bytes")
        size = source.stat().st_size
        if manifest.artifact_size is not None and manifest.artifact_size != size:
            raise DatasetRegistryError("DATASET_ARTIFACT_SIZE_MISMATCH: manifest size differs from bytes")
        if mode == "external":
            return replace(manifest, sha256=digest, artifact_size=size, storage_format="external-reference", artifact_path=str(source), source_path=manifest.source_path or str(source)), {"artifact_mode": "external", "source_format": manifest.storage_format}
        assert self.artifacts is not None
        artifact = self.artifacts.put_artifact(source)
        return replace(manifest, sha256=artifact.sha256, artifact_size=artifact.size, artifact_path=artifact.stored_path, source_path=manifest.source_path or str(source)), {"artifact_mode": "managed", "source_path": str(source), "storage": "content-addressed", "source_format": manifest.storage_format}

    def register(self, manifest: DatasetManifest, *, artifact_mode: str | None = None) -> DatasetManifest:
        self._validate_reference(manifest.dataset_id, manifest.version)
        key = (manifest.dataset_id, manifest.version)
        existing = self._manifests.get(key)
        if existing is not None:
            if existing.scientific_dataset_id == manifest.scientific_dataset_id and existing.sha256.lower() == manifest.sha256.lower():
                return existing
            raise DatasetRegistryError(f"conflicting dataset registration: {manifest.dataset_id}@{manifest.version}")
        if manifest.parent_datasets:
            self._validate_lineage(manifest)
        normalised, artifact_provenance = self._normalise_artifact(manifest, artifact_mode=artifact_mode)
        lineage = {"parent_datasets": list(normalised.parent_datasets), "transformation_run_id": normalised.transformation_run_id}
        provenance = {"artifact": artifact_provenance, "source_file_hash": normalised.source_file_hash, "redistribution_status": normalised.redistribution_status, "implementation_identity": normalised.implementation_identity, "environment_identity": normalised.environment_identity}
        record = DatasetRecord(normalised, lineage=lineage, provenance=provenance)
        if self.root is not None:
            target = self._record_path(str(record.record_id))
            if target.exists():
                raise DatasetRegistryError(f"conflicting dataset record: {record.record_id}")
            self._atomic_write_json(target, record.to_dict())
            # Read-after-write is part of registration; memory is indexed only
            # after the durable identity has been validated.
            persisted = DatasetRecord.from_mapping(json.loads(target.read_text(encoding="utf-8")))
            if persisted.record_hash != record.record_hash:
                raise DatasetRegistryError("DATASET_RECORD_HASH_MISMATCH after atomic write")
            self._record_paths[key] = target
        self._records[key] = record
        self._manifests[key] = normalised
        return normalised

    def get(self, dataset_id: str, version: str | None = None) -> DatasetManifest:
        if version is not None:
            try:
                return self._manifests[(dataset_id, version)]
            except KeyError as exc:
                raise KeyError(f"dataset not registered: {dataset_id}@{version}") from exc
        matches = [manifest for (name, _), manifest in self._manifests.items() if name == dataset_id]
        if not matches:
            raise KeyError(f"dataset not registered: {dataset_id}")
        return sorted(matches, key=lambda manifest: manifest.version)[-1]

    def get_record(self, dataset_id: str, version: str | None = None) -> DatasetRecord:
        manifest = self.get(dataset_id, version)
        return self._records[(manifest.dataset_id, manifest.version)]

    def list(self) -> tuple[DatasetManifest, ...]:
        return tuple(self._manifests.values())

    def list_records(self) -> tuple[DatasetRecord, ...]:
        return tuple(sorted(self._records.values(), key=lambda item: (item.manifest.dataset_id, item.manifest.version)))

    def list_versions(self, dataset_id: str) -> tuple[str, ...]:
        return tuple(sorted(version for name, version in self._manifests if name == dataset_id))

    def register_records(self, *, dataset_id: str, version: str, schema_id: str, records: Iterable[Mapping[str, Any]], **metadata: Any) -> DatasetManifest:
        if self.root is not None:
            self._validate_reference(dataset_id, version)
        digest, materialized = _records_hash(records)
        manifest = DatasetManifest(dataset_id, version, schema_id, digest, len(materialized), column_count=len(materialized[0]) if materialized else 0, **_manifest_kwargs({**metadata, "storage_format": "records-json"}))
        if self.root is None:
            return self.register(manifest)
        temporary = self.root / f".records-{dataset_id}-{version}.json"
        temporary.write_text(canonical_json(materialized), encoding="utf-8", newline="\n")
        try:
            return self.register(replace(manifest, artifact_path=str(temporary)), artifact_mode="managed")
        finally:
            temporary.unlink(missing_ok=True)

    def register_file(self, *, dataset_id: str, version: str, schema_id: str, path: str | Path, row_count: int | None = None, artifact_mode: str = "managed", **metadata: Any) -> DatasetManifest:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        inspection = inspect_dataset(source)
        if row_count is not None and row_count != inspection.row_count:
            raise DatasetSchemaError(f"row_count={row_count} does not match inspected row_count={inspection.row_count}")
        return self.register(DatasetManifest(dataset_id, version, schema_id, inspection.sha256, inspection.row_count, column_count=inspection.column_count, **_manifest_kwargs({**metadata, "storage_format": inspection.format, "artifact_path": source, "source_path": source})), artifact_mode=artifact_mode)

    def register_dataset(self, *, dataset_id: str, version: str, schema_id: str, path: str | Path, curated_path: str | Path | None = None, transformation_run_id: str | None = None, artifact_mode: str = "managed", **metadata: Any) -> DatasetManifest:
        source = Path(path)
        if source.suffix.lower() == ".csv" and curated_path is not None:
            manifest = convert_csv_to_parquet(source, curated_path, dataset_id=dataset_id, version=version, schema_id=schema_id, transformation_run_id=transformation_run_id, **metadata)
            return self.register(manifest, artifact_mode=artifact_mode)
        return self.register_file(dataset_id=dataset_id, version=version, schema_id=schema_id, path=source, artifact_mode=artifact_mode, transformation_run_id=transformation_run_id, **metadata)

    def write_manifest(self, manifest: DatasetManifest, directory: str | Path) -> Path:
        # Public legacy helper remains a flat manifest writer; durable register
        # uses the record envelope above.
        self._validate_reference(manifest.dataset_id, manifest.version)
        target = Path(directory) / f"{manifest.dataset_id}-{manifest.version}.manifest.json"
        self._atomic_write_json(target, manifest.to_dict())
        return target

    def load_manifests(self) -> tuple[DatasetManifest, ...]:
        return self.list() if self.root is None else tuple(record.manifest for record in self.list_records())

    @staticmethod
    def load_manifest(path: str | Path) -> DatasetManifest:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        raw = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(raw, Mapping) and raw.get("schema_version") == "research-os.dataset-record.v1":
            return DatasetRecord.from_mapping(raw).manifest
        return DatasetManifest.from_mapping(raw)

    def _persisted_record(self, key: tuple[str, str]) -> DatasetRecord:
        record = self._records[key]
        path = self._record_paths.get(key)
        if self.root is None or path is None:
            return record
        raw = json.loads(path.read_text(encoding="utf-8"))
        if record.legacy:
            return DatasetRecord(DatasetManifest.from_mapping(raw), legacy=True)
        return DatasetRecord.from_mapping(raw)

    def verify(self, dataset_id: str, version: str | None = None) -> DatasetVerification:
        manifest = self.get(dataset_id, version)
        key = (manifest.dataset_id, manifest.version)
        record = self._records[key]
        gates: list[dict[str, Any]] = []

        def result(status: str, loss: str | None) -> DatasetVerification:
            return DatasetVerification(manifest.dataset_id, manifest.version, status, loss, tuple(gates), manifest.scientific_dataset_id, manifest.sha256.lower(), record.record_id, record.legacy)

        def gate(rule_id: str, status: str, reason: str) -> None:
            gates.append({"rule_id": rule_id, "status": status, "reason": reason})

        if self.root is not None:
            try:
                persisted = self._persisted_record(key)
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                gate("DATASET-RECORD-IDENTITY", "FAIL", f"record cannot be revalidated: {exc}")
                return result("FAIL", "DATASET_RECORD_HASH_MISMATCH")
            if not record.legacy and (persisted.record_hash != record.record_hash or persisted.to_dict() != record.to_dict()):
                gate("DATASET-RECORD-IDENTITY", "FAIL", "persisted record differs from loaded identity")
                return result("FAIL", "DATASET_RECORD_HASH_MISMATCH")
            if record.legacy:
                gate("DATASET-RECORD-IDENTITY", "INSUFFICIENT_EVIDENCE", "legacy flat manifest has no durable record identity")
            else:
                gate("DATASET-RECORD-IDENTITY", "PASS", "record identity is internally consistent")
        else:
            gate("DATASET-RECORD-IDENTITY", "PASS", "memory record is internally consistent")

        if manifest.scientific_dataset_id != record.scientific_dataset_id:
            gate("DATASET-SCIENTIFIC-IDENTITY", "FAIL", "scientific identity does not reproduce")
            return result("FAIL", "DATASET_SCIENTIFIC_IDENTITY_MISMATCH")
        gate("DATASET-SCIENTIFIC-IDENTITY", "PASS", "scientific identity reproduces from canonical fields")

        if manifest.implementation_identity and record.provenance.get("implementation_identity") != manifest.implementation_identity:
            gate("DATASET-IMPLEMENTATION-PROVENANCE", "FAIL", "transformation implementation identity differs")
            return result("FAIL", "IMPLEMENTATION_IDENTITY_MISMATCH")
        gate("DATASET-IMPLEMENTATION-PROVENANCE", "PASS", "transformation implementation identity is consistent or unspecified")

        if not manifest.artifact_path:
            gate("DATASET-ARTIFACT-EXISTS", "INSUFFICIENT_EVIDENCE", "no durable artifact boundary is recorded")
            return result("INSUFFICIENT_EVIDENCE", "DATASET_ARTIFACT_NOT_DURABLE")
        artifact = Path(manifest.artifact_path)
        external = manifest.storage_format == "external-reference"
        if not external and self.root is not None:
            root_artifacts = (self.root / "artifacts").resolve()
            try:
                if not artifact.resolve().is_relative_to(root_artifacts):
                    gate("DATASET-ARTIFACT-PATH", "FAIL", "managed artifact escapes registry artifact root")
                    return result("FAIL", "DATASET_PATH_ESCAPE")
            except OSError:
                gate("DATASET-ARTIFACT-PATH", "FAIL", "managed artifact path cannot be resolved")
                return result("FAIL", "DATASET_PATH_ESCAPE")
        if not artifact.is_file():
            status = "INSUFFICIENT_EVIDENCE" if external else "FAIL"
            loss = "SOURCE_ARTIFACT_UNAVAILABLE" if external else "DATASET_ARTIFACT_MISSING"
            gate("DATASET-ARTIFACT-EXISTS", status, "artifact bytes are unavailable")
            return result(status, loss)
        if sha256_file(artifact) != manifest.sha256.lower():
            gate("DATASET-ARTIFACT-INTEGRITY", "FAIL", "artifact bytes do not match SHA-256")
            return result("FAIL", "DATASET_ARTIFACT_HASH_MISMATCH")
        gate("DATASET-ARTIFACT-INTEGRITY", "PASS", "artifact bytes and SHA-256 match")
        if manifest.artifact_size is not None and artifact.stat().st_size != manifest.artifact_size:
            gate("DATASET-ARTIFACT-SIZE", "FAIL", "artifact byte size differs")
            return result("FAIL", "DATASET_ARTIFACT_SIZE_MISMATCH")
        gate("DATASET-ARTIFACT-SIZE", "PASS", "artifact byte size matches")
        if manifest.parent_datasets:
            try:
                self._validate_lineage(manifest)
            except DatasetRegistryError as exc:
                gate("DATASET-LINEAGE", "FAIL", str(exc))
                return result("FAIL", "DATASET_PARENT_MISSING" if "PARENT_MISSING" in str(exc) else "DATASET_LINEAGE_CYCLE")
        gate("DATASET-LINEAGE", "PASS", "parent dataset lineage is acyclic and available")
        return result("PASS", None)

    def verify_dataset(self, dataset_id: str, version: str | None = None) -> bool:
        """Backward-compatible boolean facade over structured verification."""
        return self.verify(dataset_id, version).status == "PASS"

    def inspect(self, dataset_id: str, version: str | None = None, *, verify: bool = True) -> dict[str, Any]:
        record = self.get_record(dataset_id, version)
        payload = record.to_dict()
        if verify:
            payload["verification"] = self.verify(dataset_id, version).to_dict()
        return payload

    def resolve_artifact(self, dataset_id: str, version: str | None = None) -> Path:
        manifest = self.get(dataset_id, version)
        verification = self.verify(dataset_id, version)
        if verification.status != "PASS":
            raise DatasetRegistryError(f"dataset verification failed: {verification.first_loss}")
        return Path(manifest.artifact_path or "")

    @staticmethod
    def write_csv(records: Iterable[Mapping[str, Any]], path: str | Path) -> Path:
        materialized = [dict(record) for record in records]
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fields = sorted({key for record in materialized for key in record})
        with target.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(materialized)
        return target

    @staticmethod
    def read_csv(path: str | Path) -> list[dict[str, str]]:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))


@dataclass(frozen=True)
class OptionalStorageBoundary:
    """Documents the future storage engine without adding a hard dependency."""

    format: str
    engine: str

    def unavailable(self) -> StorageUnavailableError:
        return StorageUnavailableError(f"{self.engine} support is not installed for {self.format} storage")


PARQUET_STORAGE = OptionalStorageBoundary("parquet", "pyarrow/fastparquet")
DUCKDB_STORAGE = OptionalStorageBoundary("duckdb", "DuckDB")


def register_dataset(registry: DatasetRegistry, **kwargs: Any) -> DatasetManifest:
    """Functional facade for callers that do not need to hold registry state."""
    return registry.register_dataset(**kwargs)


def load_manifest(path: str | Path) -> DatasetManifest:
    return DatasetRegistry.load_manifest(path)


def verify_dataset(registry: DatasetRegistry, dataset_id: str, version: str | None = None) -> bool:
    return registry.verify_dataset(dataset_id, version)


def list_versions(registry: DatasetRegistry, dataset_id: str) -> tuple[str, ...]:
    return registry.list_versions(dataset_id)
