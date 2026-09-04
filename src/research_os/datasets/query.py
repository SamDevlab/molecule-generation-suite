from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from research_os.datasets.registry import DatasetRegistry, StorageUnavailableError


class DatasetQueryLayer:
    """Optional DuckDB query backend kept outside all Lab contracts."""

    def __init__(self, registry: DatasetRegistry):
        self.registry = registry

    def query_dataset(self, dataset_id: str, sql_or_filters: str | Mapping[str, Any], *, version: str | None = None) -> list[dict[str, Any]]:
        manifest = self.registry.get(dataset_id, version)
        if not manifest.artifact_path:
            raise ValueError("dataset manifest has no artifact_path")
        try:
            import duckdb  # type: ignore[import-not-found]
        except ImportError as exc:
            raise StorageUnavailableError("DuckDB query layer is unavailable") from exc
        connection = duckdb.connect()
        try:
            path = str(Path(manifest.artifact_path).resolve()).replace("'", "''")
            if isinstance(sql_or_filters, str):
                sql = sql_or_filters
                if "read_parquet" not in sql.lower() and "read_csv" not in sql.lower():
                    sql = f"SELECT * FROM read_parquet('{path}') WHERE {sql}"
            else:
                clauses = []
                values = []
                for key, value in sql_or_filters.items():
                    if not str(key).replace("_", "").isalnum():
                        raise ValueError(f"unsafe dataset filter column: {key}")
                    clauses.append(f'"{key}" = ?')
                    values.append(value)
                where = " AND ".join(clauses) or "TRUE"
                reader = "read_parquet" if manifest.storage_format == "parquet" else "read_csv_auto"
                sql = f"SELECT * FROM {reader}('{path}') WHERE {where}"
                return _rows(connection.execute(sql, values))
            return _rows(connection.execute(sql, [path])) if "?" in sql else _rows(connection.execute(sql))
        finally:
            connection.close()


def query_dataset(registry: DatasetRegistry, dataset_id: str, sql_or_filters: str | Mapping[str, Any], *, version: str | None = None) -> list[dict[str, Any]]:
    return DatasetQueryLayer(registry).query_dataset(dataset_id, sql_or_filters, version=version)


def _rows(result: Any) -> list[dict[str, Any]]:
    columns = [item[0] for item in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]
