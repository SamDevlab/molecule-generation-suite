from __future__ import annotations

from dataclasses import dataclass
import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from research_os.core.hashing import sha256_file, sha256_json
from research_os.core.types import EvidenceLevel
from research_os.datasets.schema import DatasetManifest, DatasetSourceType


class DatasetRegistryError(ValueError):
    pass


class StorageUnavailableError(RuntimeError):
    pass


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


class DuckDBDatasetQuery:
    """Optional read/query boundary for Parquet datasets."""

    def query(self, path: str | Path, sql: str) -> list[dict[str, Any]]:
        try:
            import duckdb  # type: ignore[import-not-found]
        except ImportError as exc:
            raise StorageUnavailableError("DuckDB support is optional and is not installed") from exc
        connection = duckdb.connect()
        try:
            return connection.execute(sql, [str(path)]).fetchdf().to_dict("records")
        finally:
            connection.close()


def _records_hash(records: Iterable[Mapping[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    materialized = [dict(record) for record in records]
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
    }


class DatasetRegistry:
    """Versioned manifest registry with CSV now and Parquet/DuckDB boundaries."""

    def __init__(self, manifests: Iterable[DatasetManifest] = ()):
        self._manifests: dict[tuple[str, str], DatasetManifest] = {}
        for manifest in manifests:
            self.register(manifest)

    def register(self, manifest: DatasetManifest) -> DatasetManifest:
        key = (manifest.dataset_id, manifest.version)
        if key in self._manifests:
            raise DatasetRegistryError(f"dataset version already registered: {manifest.dataset_id}@{manifest.version}")
        self._manifests[key] = manifest
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

    def register_records(self, *, dataset_id: str, version: str, schema_id: str, records: Iterable[Mapping[str, Any]], **metadata: Any) -> DatasetManifest:
        digest, materialized = _records_hash(records)
        manifest = DatasetManifest(dataset_id, version, schema_id, digest, len(materialized), **_manifest_kwargs(metadata))
        return self.register(manifest)

    def register_file(self, *, dataset_id: str, version: str, schema_id: str, path: str | Path, row_count: int | None = None, **metadata: Any) -> DatasetManifest:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        if row_count is None and source.suffix.lower() == ".csv":
            with source.open("r", encoding="utf-8-sig", newline="") as fh:
                row_count = max(0, sum(1 for _ in csv.DictReader(fh)))
        if row_count is None:
            raise DatasetRegistryError("row_count is required for non-CSV datasets")
        return self.register(DatasetManifest(dataset_id, version, schema_id, sha256_file(source), row_count, **_manifest_kwargs({**metadata, "storage_format": source.suffix.lower().lstrip(".") or "file"})))

    def write_manifest(self, manifest: DatasetManifest, directory: str | Path) -> Path:
        target = Path(directory) / f"{manifest.dataset_id}-{manifest.version}.manifest.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return target

    @staticmethod
    def load_manifest(path: str | Path) -> DatasetManifest:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        return DatasetManifest.from_mapping(json.loads(source.read_text(encoding="utf-8")))

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
