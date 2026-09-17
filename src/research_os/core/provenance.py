from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


class SourceType(str, Enum):
    USER_SUPPLIED = "USER_SUPPLIED"
    PUBLICATION = "PUBLICATION"
    DATASET = "DATASET"
    DATABASE = "DATABASE"
    SOFTWARE = "SOFTWARE"
    COMPUTATION = "COMPUTATION"
    SIMULATION = "SIMULATION"
    EXPERIMENT = "EXPERIMENT"
    SYNTHETIC = "SYNTHETIC"


@dataclass(frozen=True)
class ProvenanceRecord:
    """Attributable origin for an input, observation, or evidence artifact."""

    source_type: SourceType
    source_id: str
    provenance_id: str = field(default_factory=lambda: f"PRV-{uuid.uuid4().hex[:12].upper()}")
    title: str | None = None
    citation: str | None = None
    doi: str | None = None
    url: str | None = None
    license: str | None = None
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    method: str | None = None
    conditions: dict[str, Any] = field(default_factory=dict)
    parent_ids: tuple[str, ...] = ()
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source_type"] = self.source_type.value
        return data


def provenance_from_mapping(raw: dict[str, Any] | None, *, default_source_id: str = "user-input") -> ProvenanceRecord:
    raw = raw or {}
    source_type_raw = raw.get("source_type", SourceType.USER_SUPPLIED.value)
    try:
        source_type = source_type_raw if isinstance(source_type_raw, SourceType) else SourceType(str(source_type_raw))
    except ValueError:
        source_type = SourceType.USER_SUPPLIED
    return ProvenanceRecord(
        source_type=source_type,
        source_id=str(raw.get("source_id") or default_source_id),
        title=raw.get("title"), citation=raw.get("citation"), doi=raw.get("doi"),
        url=raw.get("url"), license=raw.get("license"), method=raw.get("method"),
        conditions=dict(raw.get("conditions") or {}), parent_ids=tuple(raw.get("parent_ids") or ()),
        notes=raw.get("notes"),
    )
