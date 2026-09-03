"""Source registry with content hashes and explicit review metadata."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
import json
from datetime import datetime, timezone

from research_os.core.hashing import sha256_file, sha256_json


class SourceType(str, Enum):
    PAPER = "paper"
    BOOK = "book"
    STANDARD = "standard"
    DATASET = "dataset"
    DATABASE = "database"
    REPORT = "report"
    MANUAL = "manual"
    WEB = "web"
    EXPERIMENT = "experiment"
    SIMULATION = "simulation"


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    title: str
    authors: tuple[str, ...] = ()
    organization: str | None = None
    year: int | None = None
    edition: str | None = None
    doi: str | None = None
    isbn: str | None = None
    url: str | None = None
    license: str | None = None
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    document_hash: str | None = None
    source_type: SourceType = SourceType.WEB
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "authors", tuple(self.authors))
        object.__setattr__(self, "source_type", self.source_type if isinstance(self.source_type, SourceType) else SourceType(str(self.source_type)))
        if not self.source_id.strip() or not self.title.strip():
            raise ValueError("source_id and title are required")

    @property
    def digest(self) -> str:
        return sha256_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["authors"] = list(self.authors)
        data["source_type"] = self.source_type.value
        return data

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> "SourceRecord":
        data = dict(mapping)
        data.pop("digest", None)
        data["authors"] = tuple(data.get("authors") or ())
        return cls(**data)


class SourceRegistry:
    """Small persistent source registry; registration never downloads content."""

    def __init__(self, root: str | Path | None = None, sources: Iterable[SourceRecord] = ()):
        self.root = Path(root) if root is not None else None
        self._sources: dict[str, SourceRecord] = {}
        if self.root is not None:
            (self.root / "manifests").mkdir(parents=True, exist_ok=True)
            for path in sorted((self.root / "manifests").glob("*.source.json")):
                source = SourceRecord.from_mapping(json.loads(path.read_text(encoding="utf-8")))
                self._sources[source.source_id] = source
        for source in sources:
            self.register(source)

    def register(self, source: SourceRecord) -> SourceRecord:
        if source.source_id in self._sources:
            raise ValueError(f"source already registered: {source.source_id}")
        self._sources[source.source_id] = source
        if self.root is not None:
            self.write(source)
        return source

    def get(self, source_id: str) -> SourceRecord:
        try:
            return self._sources[source_id]
        except KeyError as exc:
            raise KeyError(f"source not registered: {source_id}") from exc

    def list(self) -> tuple[SourceRecord, ...]:
        return tuple(self._sources.values())

    def write(self, source: SourceRecord) -> Path:
        if self.root is None:
            raise ValueError("SourceRegistry has no persistence root")
        target = self.root / "manifests" / f"{source.source_id}.source.json"
        target.write_text(json.dumps({**source.to_dict(), "digest": source.digest}, indent=2, ensure_ascii=False), encoding="utf-8")
        return target

    def register_file(self, *, source_id: str, title: str, path: str | Path, source_type: SourceType | str = SourceType.WEB, **metadata: Any) -> SourceRecord:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        record = SourceRecord(source_id, title, document_hash=sha256_file(source), source_type=source_type, metadata={"path": str(source), **metadata})
        return self.register(record)

    def verify_document(self, source_id: str, path: str | Path | None = None) -> bool:
        record = self.get(source_id)
        target = Path(path or record.metadata.get("path", ""))
        return bool(record.document_hash and target.is_file() and sha256_file(target) == record.document_hash)

