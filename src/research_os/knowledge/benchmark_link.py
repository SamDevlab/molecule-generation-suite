"""Bridge reviewed knowledge notes to immutable benchmark identities.

This module intentionally reuses the existing Research OS SourceRecord and
Zettel models instead of introducing a parallel knowledge model.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from research_os.core.hashing import sha256_json
from research_os.core.types import EvidenceLevel
from research_os.knowledge.source import SourceRecord, SourceType
from research_os.knowledge.zettel import ReviewStatus, SourceLocator, Zettel, ZettelType

_SCHEMA = "research-os.benchmark-knowledge.v1"


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
        self.validate_shape()

    def validate_shape(self) -> None:
        required = (self.link_id, self.benchmark_id, self.protocol_id, self.scientific_result_hash)
        if any(not value.strip() for value in required):
            raise ValueError("benchmark knowledge links require non-empty identity fields")
        if len(self.scientific_result_hash) != 64 or any(char not in "0123456789abcdef" for char in self.scientific_result_hash.lower()):
            raise ValueError("scientific_result_hash must be a SHA-256 hex digest")
        if not self.source_ids or not self.zettel_ids:
            raise ValueError("benchmark knowledge links require at least one source and one reviewed note")

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
        return sha256_json(self.to_dict())


def _locator_is_specific(locator: SourceLocator) -> bool:
    return bool(locator.page or locator.chapter or locator.section)


def validate_benchmark_knowledge_link(
    link: BenchmarkKnowledgeLink,
    *,
    sources: Iterable[SourceRecord],
    zettels: Iterable[Zettel],
) -> None:
    link.validate_shape()
    source_map = {source.source_id: source for source in sources}
    zettel_map = {zettel.zettel_id: zettel for zettel in zettels}

    missing_sources = set(link.source_ids) - source_map.keys()
    if missing_sources:
        raise ValueError(f"unknown source IDs: {sorted(missing_sources)}")
    missing_zettels = set(link.zettel_ids) - zettel_map.keys()
    if missing_zettels:
        raise ValueError(f"unknown zettel IDs: {sorted(missing_zettels)}")

    for zettel_id in link.zettel_ids:
        zettel = zettel_map[zettel_id]
        if zettel.review_status != ReviewStatus.VERIFIED:
            raise ValueError(f"benchmark-linked zettel must be VERIFIED: {zettel_id}")
        if not zettel.sources:
            raise ValueError(f"benchmark-linked zettel lacks source locators: {zettel_id}")
        for locator in zettel.sources:
            if locator.source_id not in source_map:
                raise ValueError(f"zettel {zettel_id} references unknown source {locator.source_id}")
            if not _locator_is_specific(locator):
                raise ValueError(
                    f"benchmark-linked zettel requires page/chapter/section locator: {zettel_id}"
                )


def _source_payload(source: SourceRecord) -> dict[str, Any]:
    data = source.to_dict()
    data.pop("retrieved_at", None)
    return data


def _zettel_payload(zettel: Zettel) -> dict[str, Any]:
    data = zettel.to_dict()
    data.pop("created_at", None)
    return data


def benchmark_knowledge_identity(
    *,
    sources: Iterable[SourceRecord],
    zettels: Iterable[Zettel],
    links: Iterable[BenchmarkKnowledgeLink],
) -> str:
    source_items = sorted(sources, key=lambda item: item.source_id)
    zettel_items = sorted(zettels, key=lambda item: item.zettel_id)
    link_items = sorted(links, key=lambda item: item.link_id)
    for link in link_items:
        validate_benchmark_knowledge_link(link, sources=source_items, zettels=zettel_items)
    return sha256_json(
        {
            "schema": _SCHEMA,
            "sources": [_source_payload(item) for item in source_items],
            "zettels": [_zettel_payload(item) for item in zettel_items],
            "links": [item.to_dict() for item in link_items],
        }
    )


def bundle_from_mapping(payload: dict[str, Any]) -> tuple[list[SourceRecord], list[Zettel], list[BenchmarkKnowledgeLink]]:
    if payload.get("schema") != _SCHEMA:
        raise ValueError("unsupported benchmark knowledge schema")

    sources: list[SourceRecord] = []
    for raw in payload.get("sources", []):
        data = dict(raw)
        data["authors"] = tuple(data.get("authors") or ())
        data["source_type"] = SourceType(data.get("source_type", SourceType.WEB.value))
        sources.append(SourceRecord(**data))

    zettels: list[Zettel] = []
    for raw in payload.get("zettels", []):
        data = dict(raw)
        data["zettel_type"] = ZettelType(data["zettel_type"])
        data["evidence_level"] = EvidenceLevel(data["evidence_level"])
        data["review_status"] = ReviewStatus(data["review_status"])
        data["limitations"] = tuple(data.get("limitations") or ())
        data["tags"] = tuple(data.get("tags") or ())
        data["links"] = tuple(data.get("links") or ())
        data["sources"] = tuple(SourceLocator(**item) for item in data.get("sources") or ())
        zettels.append(Zettel(**data))

    links = [BenchmarkKnowledgeLink(**{**raw, "source_ids": tuple(raw.get("source_ids") or ()), "zettel_ids": tuple(raw.get("zettel_ids") or ())}) for raw in payload.get("links", [])]
    for link in links:
        validate_benchmark_knowledge_link(link, sources=sources, zettels=zettels)
    return sources, zettels, links


def verify_bundle(payload: dict[str, Any]) -> str:
    sources, zettels, links = bundle_from_mapping(payload)
    expected = payload.get("knowledge_identity")
    actual = benchmark_knowledge_identity(sources=sources, zettels=zettels, links=links)
    if expected is not None and expected != actual:
        raise ValueError(f"knowledge identity mismatch: expected {expected}, got {actual}")
    return actual
