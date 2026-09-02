from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Iterable, Mapping

from research_os.core.hashing import sha256_json
from research_os.core.types import EvidenceLevel


class DatasetSourceType(str, Enum):
    TEST_SYNTHETIC = "TEST_SYNTHETIC"
    EXPERIMENTAL = "EXPERIMENTAL"
    EXPERIMENT = "EXPERIMENTAL"
    CURATED_EXPERIMENTAL = "CURATED_EXPERIMENTAL"
    DFT = "DFT"
    CALPHAD = "CALPHAD"
    PHYSICS_SIMULATION = "PHYSICS_SIMULATION"
    PHYSICS = "PHYSICS_SIMULATION"
    ML_GENERATED = "ML_GENERATED"
    ML_PREDICTION = "ML_GENERATED"
    HEURISTIC_GENERATED = "HEURISTIC_GENERATED"
    HEURISTIC = "HEURISTIC_GENERATED"

    @property
    def is_synthetic(self) -> bool:
        return self in {self.TEST_SYNTHETIC, self.ML_GENERATED, self.HEURISTIC_GENERATED}

    @property
    def is_computational(self) -> bool:
        return self in {self.DFT, self.CALPHAD, self.PHYSICS_SIMULATION}


def _source_type(value: DatasetSourceType | str) -> DatasetSourceType:
    if isinstance(value, DatasetSourceType):
        return value
    try:
        return DatasetSourceType(str(value).upper())
    except ValueError as exc:
        raise ValueError(f"unsupported dataset source type: {value}") from exc


def _values(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    return tuple(value)


def _levels(values: Iterable[EvidenceLevel | str]) -> tuple[EvidenceLevel, ...]:
    result: list[EvidenceLevel] = []
    for value in values:
        level = value if isinstance(value, EvidenceLevel) else EvidenceLevel(str(value))
        if level not in result:
            result.append(level)
    return tuple(result)


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    version: str
    schema_id: str
    sha256: str
    row_count: int
    column_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sources: tuple[str, ...] = ()
    licenses: tuple[str, ...] = ()
    source_types: tuple[DatasetSourceType, ...] = ()
    evidence_levels: tuple[EvidenceLevel, ...] = ()
    synthetic_fraction: float = 0.0
    experimental_fraction: float = 0.0
    computational_fraction: float = 0.0
    parent_datasets: tuple[str, ...] = ()
    transformation_run_id: str | None = None
    notes: str | None = None
    storage_format: str = "records"
    source_file_hash: str | None = None
    artifact_path: str | None = None
    source_path: str | None = None

    def __post_init__(self) -> None:
        if not self.dataset_id.strip() or not self.version.strip() or not self.schema_id.strip():
            raise ValueError("dataset_id, version and schema_id are required")
        if self.row_count < 0:
            raise ValueError("row_count cannot be negative")
        if self.column_count < 0:
            raise ValueError("column_count cannot be negative")
        if len(self.sha256) != 64 or any(character not in "0123456789abcdefABCDEF" for character in self.sha256):
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        object.__setattr__(self, "sources", _values(self.sources))
        object.__setattr__(self, "licenses", tuple(str(value) for value in _values(self.licenses)))
        object.__setattr__(self, "parent_datasets", tuple(str(value) for value in _values(self.parent_datasets)))
        object.__setattr__(self, "source_types", tuple(_source_type(value) for value in _values(self.source_types)))
        object.__setattr__(self, "evidence_levels", _levels(_values(self.evidence_levels)))
        fractions = (self.synthetic_fraction, self.experimental_fraction, self.computational_fraction)
        if any(not math.isfinite(float(value)) or not 0 <= float(value) <= 1 for value in fractions):
            raise ValueError("dataset fractions must be finite values in [0,1]")
        if sum(fractions) > 1.0 + 1e-9:
            raise ValueError("synthetic, experimental and computational fractions cannot sum above one")

    @property
    def is_synthetic(self) -> bool:
        return self.synthetic_fraction > 0 or any(source.is_synthetic for source in self.source_types)

    @property
    def is_experimental_ground_truth(self) -> bool:
        from research_os.datasets.gates import is_experimental_ground_truth
        return is_experimental_ground_truth(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "schema_id": self.schema_id,
            "sha256": self.sha256,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "created_at": self.created_at,
            "sources": list(self.sources),
            "licenses": list(self.licenses),
            "source_types": [source.value for source in self.source_types],
            "evidence_levels": [level.value for level in self.evidence_levels],
            "synthetic_fraction": self.synthetic_fraction,
            "experimental_fraction": self.experimental_fraction,
            "computational_fraction": self.computational_fraction,
            "parent_datasets": list(self.parent_datasets),
            "transformation_run_id": self.transformation_run_id,
            "notes": self.notes,
            "storage_format": self.storage_format,
            "source_file_hash": self.source_file_hash,
            "artifact_path": self.artifact_path,
            "source_path": self.source_path,
        }

    @classmethod
    def from_records(cls, *, dataset_id: str, version: str, schema_id: str, records: Iterable[Mapping[str, Any]], **metadata: Any) -> "DatasetManifest":
        materialized = [dict(record) for record in records]
        if materialized:
            expected = set(materialized[0])
            if any(set(record) != expected for record in materialized[1:]):
                raise ValueError("records have inconsistent column schemas")
        column_count = int(metadata.pop("column_count", len(materialized[0]) if materialized else 0))
        return cls(dataset_id, version, schema_id, sha256_json(materialized), len(materialized), column_count=column_count, **metadata)

    @classmethod
    def from_file(cls, *, dataset_id: str, version: str, schema_id: str, path: str, row_count: int, column_count: int = 0, **metadata: Any) -> "DatasetManifest":
        from research_os.core.hashing import sha256_file
        return cls(dataset_id, version, schema_id, sha256_file(path), row_count, column_count=column_count, artifact_path=path, **metadata)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "DatasetManifest":
        return cls(
            dataset_id=str(raw["dataset_id"]), version=str(raw["version"]), schema_id=str(raw["schema_id"]), sha256=str(raw["sha256"]), row_count=int(raw["row_count"]), column_count=int(raw.get("column_count", 0)), created_at=str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()), sources=_values(raw.get("sources")), licenses=_values(raw.get("licenses")), source_types=_values(raw.get("source_types")), evidence_levels=_values(raw.get("evidence_levels")), synthetic_fraction=float(raw.get("synthetic_fraction", 0.0)), experimental_fraction=float(raw.get("experimental_fraction", 0.0)), computational_fraction=float(raw.get("computational_fraction", 0.0)), parent_datasets=_values(raw.get("parent_datasets")), transformation_run_id=raw.get("transformation_run_id"), notes=raw.get("notes"), storage_format=str(raw.get("storage_format", "records")), source_file_hash=raw.get("source_file_hash"), artifact_path=raw.get("artifact_path"), source_path=raw.get("source_path"),
        )


DatasetType = DatasetSourceType
