"""Canonical, source-first knowledge records for Research OS.

The first implementation is deliberately small and file-oriented. It keeps
scientific claims auditable before adding databases, embeddings, or automated
PDF ingestion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any, Literal

SourceKind = Literal["paper", "book", "dataset", "webpage", "benchmark", "experiment"]
ClaimStatus = Literal["SUPPORTED", "CONTESTED", "HYPOTHESIS", "REJECTED"]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def scientific_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    kind: SourceKind
    title: str
    authors: tuple[str, ...] = ()
    year: int | None = None
    doi: str | None = None
    isbn: str | None = None
    url: str | None = None
    license: str | None = None

    def validate(self) -> None:
        if not self.source_id.strip() or not self.title.strip():
            raise ValueError("source_id and title are required")
        if not any((self.doi, self.isbn, self.url)) and self.kind not in {"benchmark", "experiment"}:
            raise ValueError("external sources require DOI, ISBN, or URL provenance")

    @property
    def content_hash(self) -> str:
        self.validate()
        return scientific_hash(asdict(self))


@dataclass(frozen=True)
class NoteRecord:
    note_id: str
    source_id: str
    locator: str
    summary: str
    tags: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.note_id.strip() or not self.source_id.strip():
            raise ValueError("note_id and source_id are required")
        if not self.locator.strip():
            raise ValueError("source notes require an exact locator (page, table, section, etc.)")
        if not self.summary.strip():
            raise ValueError("note summary is required")

    @property
    def content_hash(self) -> str:
        self.validate()
        return scientific_hash(asdict(self))


@dataclass(frozen=True)
class ClaimRecord:
    claim_id: str
    statement: str
    status: ClaimStatus
    note_ids: tuple[str, ...] = ()
    scope: str = ""

    def validate(self) -> None:
        if not self.claim_id.strip() or not self.statement.strip():
            raise ValueError("claim_id and statement are required")
        if self.status != "HYPOTHESIS" and not self.note_ids:
            raise ValueError("Sem fonte, sem fato: non-hypothesis claims require at least one source note")

    @property
    def content_hash(self) -> str:
        self.validate()
        return scientific_hash(asdict(self))


@dataclass(frozen=True)
class EvidenceLink:
    evidence_id: str
    claim_id: str
    benchmark_id: str
    protocol_id: str
    scientific_result_hash: str
    artifact_id: str | None = None
    notes: str = ""

    def validate(self) -> None:
        required = (self.evidence_id, self.claim_id, self.benchmark_id, self.protocol_id, self.scientific_result_hash)
        if any(not item.strip() for item in required):
            raise ValueError("evidence links require claim, benchmark, protocol, and scientific result identity")

    @property
    def content_hash(self) -> str:
        self.validate()
        return scientific_hash(asdict(self))


@dataclass
class KnowledgeBundle:
    sources: list[SourceRecord] = field(default_factory=list)
    notes: list[NoteRecord] = field(default_factory=list)
    claims: list[ClaimRecord] = field(default_factory=list)
    evidence: list[EvidenceLink] = field(default_factory=list)

    def validate(self) -> None:
        for collection in (self.sources, self.notes, self.claims, self.evidence):
            for record in collection:
                record.validate()

        source_ids = {record.source_id for record in self.sources}
        note_ids = {record.note_id for record in self.notes}
        claim_ids = {record.claim_id for record in self.claims}

        if len(source_ids) != len(self.sources) or len(note_ids) != len(self.notes) or len(claim_ids) != len(self.claims):
            raise ValueError("knowledge record IDs must be unique")
        for note in self.notes:
            if note.source_id not in source_ids:
                raise ValueError(f"note {note.note_id} references unknown source {note.source_id}")
        for claim in self.claims:
            missing = set(claim.note_ids) - note_ids
            if missing:
                raise ValueError(f"claim {claim.claim_id} references unknown notes: {sorted(missing)}")
        for link in self.evidence:
            if link.claim_id not in claim_ids:
                raise ValueError(f"evidence {link.evidence_id} references unknown claim {link.claim_id}")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema": "research-os.knowledge.v1",
            "sources": [asdict(record) for record in sorted(self.sources, key=lambda r: r.source_id)],
            "notes": [asdict(record) for record in sorted(self.notes, key=lambda r: r.note_id)],
            "claims": [asdict(record) for record in sorted(self.claims, key=lambda r: r.claim_id)],
            "evidence": [asdict(record) for record in sorted(self.evidence, key=lambda r: r.evidence_id)],
        }

    @property
    def scientific_identity(self) -> str:
        payload = self.to_dict().copy()
        payload.pop("schema")
        return scientific_hash(payload)


def bundle_from_dict(payload: dict[str, Any]) -> KnowledgeBundle:
    if payload.get("schema") != "research-os.knowledge.v1":
        raise ValueError("unsupported knowledge schema")

    bundle = KnowledgeBundle(
        sources=[
            SourceRecord(**{**record, "authors": tuple(record.get("authors", ()))})
            for record in payload.get("sources", [])
        ],
        notes=[
            NoteRecord(**{**record, "tags": tuple(record.get("tags", ()))})
            for record in payload.get("notes", [])
        ],
        claims=[
            ClaimRecord(**{**record, "note_ids": tuple(record.get("note_ids", ()))})
            for record in payload.get("claims", [])
        ],
        evidence=[EvidenceLink(**record) for record in payload.get("evidence", [])],
    )
    bundle.validate()
    return bundle


def bundle_from_json(text: str) -> KnowledgeBundle:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("knowledge bundle root must be an object")
    return bundle_from_dict(payload)


def bundle_to_json(bundle: KnowledgeBundle, *, pretty: bool = True) -> str:
    payload = bundle.to_dict()
    if pretty:
        return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    return canonical_json(payload)
