"""Bridge reviewed knowledge notes to immutable benchmark identities.

This module intentionally reuses the existing Research OS ``SourceRecord``
and ``Zettel`` models instead of introducing a parallel knowledge model.
``BenchmarkKnowledgeLink`` is the small evidence bridge from reviewed notes
to a benchmark/protocol scientific result identity.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from typing import Any

from research_os.core.hashing import sha256_json
from research_os.core.types import EvidenceLevel
from research_os.knowledge.source import SourceRecord, SourceType
from research_os.knowledge.zettel import ReviewStatus, SourceLocator, Zettel, ZettelType

_SCHEMA = "research-os.benchmark-knowledge.v1"
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_BUNDLE_FIELDS = frozenset({"schema", "knowledge_identity", "sources", "zettels", "links"})
_EXTERNAL_SOURCE_PROVENANCE = {
    SourceType.PAPER: ("doi", "url"),
    SourceType.BOOK: ("isbn", "doi", "url"),
    SourceType.DATASET: ("doi", "url"),
    SourceType.WEB: ("url",),
}


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _normalize_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a SHA-256 hex digest")
    return value.lower()


def _as_sequence(value: Any, field: str) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)):
        raise ValueError(f"{field} must be a list or tuple")
    try:
        return tuple(value)
    except TypeError as exc:
        raise ValueError(f"{field} must be a list or tuple") from exc


def _validate_unique_ids(records: Iterable[Any], *, field: str, label: str) -> tuple[Any, ...]:
    items = tuple(records)
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in items:
        value = getattr(item, field, None)
        _require_text(value, f"{label} {field}")
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        raise ValueError(f"duplicate {label} {field}: {sorted(duplicates)}")
    return items


def _validate_unique_references(values: Iterable[Any], *, field: str) -> tuple[str, ...]:
    items = tuple(values)
    normalized = tuple(_require_text(value, field) for value in items)
    if len(set(normalized)) != len(normalized):
        duplicates = sorted({value for value in normalized if normalized.count(value) > 1})
        raise ValueError(f"duplicate {field}: {duplicates}")
    return normalized


def _validate_source(source: SourceRecord) -> None:
    _require_text(source.source_id, "source_id")
    _require_text(source.title, f"source {source.source_id} title")
    if source.document_hash is not None:
        _normalize_sha256(source.document_hash, f"source {source.source_id} document_hash")
    required_fields = _EXTERNAL_SOURCE_PROVENANCE.get(source.source_type)
    if required_fields and not any(getattr(source, field, None) for field in required_fields):
        fields = "/".join(required_fields)
        raise ValueError(f"source {source.source_id} requires external provenance: {fields}")


def _locator_is_specific(locator: SourceLocator) -> bool:
    return any(
        isinstance(value, str) and bool(value.strip())
        for value in (locator.page, locator.chapter, locator.section)
    )


def _validate_zettel(zettel: Zettel, *, source_map: Mapping[str, SourceRecord]) -> None:
    _require_text(zettel.zettel_id, "zettel_id")
    if not zettel.sources:
        raise ValueError(f"zettel {zettel.zettel_id} requires at least one source locator")
    for locator in zettel.sources:
        _require_text(locator.source_id, f"zettel {zettel.zettel_id} locator source_id")
        if locator.source_id not in source_map:
            raise ValueError(f"zettel {zettel.zettel_id} references unknown source {locator.source_id}")
        if not _locator_is_specific(locator):
            raise ValueError(
                f"zettel {zettel.zettel_id} requires page/chapter/section locator"
            )


def _validate_records(
    sources: Iterable[SourceRecord],
    zettels: Iterable[Zettel],
) -> tuple[tuple[SourceRecord, ...], tuple[Zettel, ...]]:
    source_items = _validate_unique_ids(sources, field="source_id", label="source")
    zettel_items = _validate_unique_ids(zettels, field="zettel_id", label="zettel")
    for source in source_items:
        _validate_source(source)
    source_map = {source.source_id: source for source in source_items}
    for zettel in zettel_items:
        _validate_zettel(zettel, source_map=source_map)
    return source_items, zettel_items


@dataclass(frozen=True)
class BenchmarkKnowledgeLink:
    link_id: str
    benchmark_id: str
    protocol_id: str
    scientific_result_hash: str
    source_ids: tuple[str, ...]
    zettel_ids: tuple[str, ...]
    artifact_id: str | None = None
    boundary: str = "pre-result"
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_ids", tuple(self.source_ids))
        object.__setattr__(self, "zettel_ids", tuple(self.zettel_ids))
        object.__setattr__(
            self,
            "scientific_result_hash",
            _normalize_sha256(self.scientific_result_hash, "scientific_result_hash"),
        )
        self.validate_shape()

    def validate_shape(self) -> None:
        required = (self.link_id, self.benchmark_id, self.protocol_id, self.scientific_result_hash)
        for field, value in zip(("link_id", "benchmark_id", "protocol_id", "scientific_result_hash"), required):
            _require_text(value, field)
        _normalize_sha256(self.scientific_result_hash, "scientific_result_hash")
        if not self.source_ids or not self.zettel_ids:
            raise ValueError("benchmark knowledge links require at least one source and one reviewed note")
        _validate_unique_references(self.source_ids, field="source_ids")
        _validate_unique_references(self.zettel_ids, field="zettel_ids")

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_id": self.link_id,
            "benchmark_id": self.benchmark_id,
            "protocol_id": self.protocol_id,
            "scientific_result_hash": self.scientific_result_hash,
            "source_ids": list(self.source_ids),
            "zettel_ids": list(self.zettel_ids),
            "artifact_id": self.artifact_id,
            "boundary": self.boundary,
            "notes": self.notes,
        }

    @property
    def digest(self) -> str:
        return sha256_json(self.scientific_dict())

    def scientific_dict(self) -> dict[str, Any]:
        """Return the identity-bearing fields of this evidence link.

        ``artifact_id`` identifies an execution artifact and is deliberately
        excluded.  Repackaging or relocating the same scientific result must
        not create a new scientific knowledge identity.
        """
        return {
            "link_id": self.link_id,
            "benchmark_id": self.benchmark_id,
            "protocol_id": self.protocol_id,
            "scientific_result_hash": self.scientific_result_hash,
            "source_ids": sorted(self.source_ids),
            "zettel_ids": sorted(self.zettel_ids),
            "boundary": self.boundary,
            "notes": self.notes,
        }


def validate_benchmark_knowledge_link(
    link: BenchmarkKnowledgeLink,
    *,
    sources: Iterable[SourceRecord],
    zettels: Iterable[Zettel],
) -> None:
    source_items = _validate_unique_ids(sources, field="source_id", label="source")
    zettel_items = _validate_unique_ids(zettels, field="zettel_id", label="zettel")
    for source in source_items:
        _validate_source(source)
    link.validate_shape()
    source_map = {source.source_id: source for source in source_items}
    zettel_map = {zettel.zettel_id: zettel for zettel in zettel_items}

    missing_sources = set(link.source_ids) - source_map.keys()
    if missing_sources:
        raise ValueError(f"unknown source IDs: {sorted(missing_sources)}")
    missing_zettels = set(link.zettel_ids) - zettel_map.keys()
    if missing_zettels:
        raise ValueError(f"unknown zettel IDs: {sorted(missing_zettels)}")

    for zettel in zettel_items:
        _validate_zettel(zettel, source_map=source_map)

    for zettel_id in link.zettel_ids:
        zettel = zettel_map[zettel_id]
        if zettel.review_status != ReviewStatus.VERIFIED:
            raise ValueError(f"benchmark-linked zettel must be VERIFIED: {zettel_id}")
        for locator in zettel.sources:
            if locator.source_id not in link.source_ids:
                raise ValueError(
                    f"benchmark link {link.link_id} omits locator source {locator.source_id}"
                )


def _source_payload(source: SourceRecord) -> dict[str, Any]:
    data = source.to_dict()
    data.pop("retrieved_at", None)
    return data


def _zettel_payload(zettel: Zettel) -> dict[str, Any]:
    data = zettel.to_dict()
    data.pop("created_at", None)
    data["tags"] = sorted(data.get("tags") or ())
    data["links"] = sorted(data.get("links") or ())
    data["sources"] = sorted(
        data.get("sources") or (),
        key=lambda item: (
            item.get("source_id", ""),
            item.get("chapter") or "",
            item.get("page") or "",
            item.get("section") or "",
            item.get("doi") or "",
            item.get("url") or "",
        ),
    )
    return data


def benchmark_knowledge_identity(
    *,
    sources: Iterable[SourceRecord],
    zettels: Iterable[Zettel],
    links: Iterable[BenchmarkKnowledgeLink],
) -> str:
    source_items, zettel_items = _validate_records(sources, zettels)
    link_items = _validate_unique_ids(links, field="link_id", label="evidence link")
    source_items = tuple(sorted(source_items, key=lambda item: item.source_id))
    zettel_items = tuple(sorted(zettel_items, key=lambda item: item.zettel_id))
    link_items = tuple(sorted(link_items, key=lambda item: item.link_id))
    for link in link_items:
        validate_benchmark_knowledge_link(link, sources=source_items, zettels=zettel_items)
    return sha256_json(
        {
            "schema": _SCHEMA,
            "sources": [_source_payload(item) for item in source_items],
            "zettels": [_zettel_payload(item) for item in zettel_items],
            "links": [item.scientific_dict() for item in link_items],
        }
    )


def bundle_from_mapping(payload: dict[str, Any]) -> tuple[list[SourceRecord], list[Zettel], list[BenchmarkKnowledgeLink]]:
    if not isinstance(payload, Mapping):
        raise ValueError("knowledge bundle must be a JSON object")
    unknown_fields = set(payload) - _BUNDLE_FIELDS
    if unknown_fields:
        raise ValueError(f"unsupported knowledge bundle fields: {sorted(unknown_fields)}")
    if payload.get("schema") != _SCHEMA:
        raise ValueError("unsupported benchmark knowledge schema")

    sources: list[SourceRecord] = []
    for raw in _as_sequence(payload.get("sources", []), "sources"):
        if not isinstance(raw, Mapping):
            raise ValueError("each source must be a JSON object")
        data = dict(raw)
        data.pop("digest", None)
        data["authors"] = tuple(data.get("authors") or ())
        data["source_type"] = SourceType(data.get("source_type", SourceType.WEB.value))
        sources.append(SourceRecord(**data))

    zettels: list[Zettel] = []
    for raw in _as_sequence(payload.get("zettels", []), "zettels"):
        if not isinstance(raw, Mapping):
            raise ValueError("each zettel must be a JSON object")
        data = dict(raw)
        data.pop("digest", None)
        data["zettel_type"] = ZettelType(data["zettel_type"])
        data["evidence_level"] = EvidenceLevel(data["evidence_level"])
        data["review_status"] = ReviewStatus(data["review_status"])
        data["limitations"] = tuple(data.get("limitations") or ())
        data["tags"] = tuple(data.get("tags") or ())
        data["links"] = tuple(data.get("links") or ())
        data["conditions"] = dict(data.get("conditions") or {})
        data["sources"] = tuple(
            SourceLocator(**item)
            for item in _as_sequence(data.get("sources"), "zettel.sources")
            if isinstance(item, Mapping)
        )
        if len(data["sources"]) != len(_as_sequence(data.get("sources"), "zettel.sources")):
            raise ValueError("each zettel source locator must be a JSON object")
        zettels.append(Zettel(**data))

    links: list[BenchmarkKnowledgeLink] = []
    for raw in _as_sequence(payload.get("links", []), "links"):
        if not isinstance(raw, Mapping):
            raise ValueError("each evidence link must be a JSON object")
        links.append(
            BenchmarkKnowledgeLink(
                **{
                    **raw,
                    "source_ids": _as_sequence(raw.get("source_ids"), "link.source_ids"),
                    "zettel_ids": _as_sequence(raw.get("zettel_ids"), "link.zettel_ids"),
                }
            )
        )
    _validate_records(sources, zettels)
    _validate_unique_ids(links, field="link_id", label="evidence link")
    for link in links:
        validate_benchmark_knowledge_link(link, sources=sources, zettels=zettels)
    return sources, zettels, links


def verify_bundle(payload: dict[str, Any]) -> str:
    sources, zettels, links = bundle_from_mapping(payload)
    expected = payload.get("knowledge_identity")
    actual = benchmark_knowledge_identity(sources=sources, zettels=zettels, links=links)
    if expected is not None and _normalize_sha256(expected, "knowledge_identity") != actual:
        raise ValueError(f"knowledge identity mismatch: expected {expected}, got {actual}")
    return actual
