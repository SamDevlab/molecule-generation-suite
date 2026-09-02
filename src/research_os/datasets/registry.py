from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from research_os.core.hashing import sha256_file, sha256_json
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
            "source_file_hash": sha256_file(source),
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
    }


class DatasetRegistry:
    """Versioned manifest registry with CSV now and Parquet/DuckDB boundaries."""

    def __init__(self, manifests: Iterable[DatasetManifest] = (), *, root: str | Path | None = None):
        self._manifests: dict[tuple[str, str], DatasetManifest] = {}
        self.root = Path(root) if root is not None else None
        if self.root is not None:
            for directory in ("manifests", "raw", "curated", "external", "synthetic"):
                (self.root / directory).mkdir(parents=True, exist_ok=True)
            for path in sorted((self.root / "manifests").glob("*.manifest.json")):
                manifest = self.load_manifest(path)
                self._manifests[(manifest.dataset_id, manifest.version)] = manifest
        for manifest in manifests:
            self.register(manifest)

    def register(self, manifest: DatasetManifest) -> DatasetManifest:
        key = (manifest.dataset_id, manifest.version)
        if key in self._manifests:
            raise DatasetRegistryError(f"dataset version already registered: {manifest.dataset_id}@{manifest.version}")
        self._manifests[key] = manifest
        if self.root is not None:
            self.write_manifest(manifest, self.root / "manifests")
        return manifest

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

    def list(self) -> tuple[DatasetManifest, ...]:
        return tuple(self._manifests.values())

    def list_versions(self, dataset_id: str) -> tuple[str, ...]:
        return tuple(sorted(version for name, version in self._manifests if name == dataset_id))

    def register_records(self, *, dataset_id: str, version: str, schema_id: str, records: Iterable[Mapping[str, Any]], **metadata: Any) -> DatasetManifest:
        digest, materialized = _records_hash(records)
        manifest = DatasetManifest(dataset_id, version, schema_id, digest, len(materialized), column_count=len(materialized[0]) if materialized else 0, **_manifest_kwargs(metadata))
        return self.register(manifest)

    def register_file(self, *, dataset_id: str, version: str, schema_id: str, path: str | Path, row_count: int | None = None, **metadata: Any) -> DatasetManifest:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        inspection = inspect_dataset(source)
        if row_count is not None and row_count != inspection.row_count:
            raise DatasetSchemaError(f"row_count={row_count} does not match inspected row_count={inspection.row_count}")
        return self.register(DatasetManifest(dataset_id, version, schema_id, inspection.sha256, inspection.row_count, column_count=inspection.column_count, **_manifest_kwargs({**metadata, "storage_format": inspection.format, "artifact_path": source, "source_path": source})))

    def register_dataset(self, *, dataset_id: str, version: str, schema_id: str, path: str | Path, curated_path: str | Path | None = None, transformation_run_id: str | None = None, **metadata: Any) -> DatasetManifest:
        source = Path(path)
        if source.suffix.lower() == ".csv" and curated_path is not None:
            manifest = convert_csv_to_parquet(source, curated_path, dataset_id=dataset_id, version=version, schema_id=schema_id, transformation_run_id=transformation_run_id, **metadata)
            return self.register(manifest)
        return self.register_file(dataset_id=dataset_id, version=version, schema_id=schema_id, path=source, transformation_run_id=transformation_run_id, **metadata)

    def write_manifest(self, manifest: DatasetManifest, directory: str | Path) -> Path:
        target = Path(directory) / f"{manifest.dataset_id}-{manifest.version}.manifest.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return target

    def load_manifests(self) -> tuple[DatasetManifest, ...]:
        if self.root is None:
            return self.list()
        return tuple(self.load_manifest(path) for path in sorted((self.root / "manifests").glob("*.manifest.json")))

    @staticmethod
    def load_manifest(path: str | Path) -> DatasetManifest:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        return DatasetManifest.from_mapping(json.loads(source.read_text(encoding="utf-8")))

    def verify_dataset(self, dataset_id: str, version: str | None = None) -> bool:
        manifest = self.get(dataset_id, version)
        if not manifest.artifact_path:
            raise DatasetRegistryError("dataset manifest has no artifact_path to verify")
        artifact = Path(manifest.artifact_path)
        if not artifact.is_file():
            return False
        return sha256_file(artifact) == manifest.sha256

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
