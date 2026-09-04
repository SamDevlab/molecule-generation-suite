"""Private-corpus metadata, ingestion and review gates.

The module deliberately keeps private document content in memory during
extraction.  Only hashes, filenames, provenance metadata and review queue
items are persisted.  Candidate material is never promoted to VERIFIED by
ingestion, and source text is never treated as executable instructions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
import uuid

from research_os.core.hashing import sha256_file, sha256_json
from research_os.knowledge.ingestion import (
    IngestionResult,
    IngestionStatus,
    KnowledgeIngestionPipeline,
    ReviewItem,
)
from research_os.knowledge.source import SourceRecord, SourceType
from research_os.knowledge.zettel import ReviewStatus


class PrivateConfidentiality(str, Enum):
    PRIVATE_USER_SOURCE = "PRIVATE_USER_SOURCE"
    INTERNAL_PROJECT_SOURCE = "INTERNAL_PROJECT_SOURCE"
    PUBLIC_SOURCE = "PUBLIC_SOURCE"


class CorpusReadinessStatus(str, Enum):
    INFRASTRUCTURE_READY_AWAITING_USER_CORPUS = "INFRASTRUCTURE_READY_AWAITING_USER_CORPUS"
    INGESTED_REVIEW_REQUIRED = "INGESTED_REVIEW_REQUIRED"
    READY_FOR_CORPUS_RESEARCH = "READY_FOR_CORPUS_RESEARCH"


@dataclass(frozen=True)
class PrivateSourceRecord:
    """Non-content record for a user-provided document."""

    source_id: str
    filename: str
    content_hash: str
    source_type: str
    title: str
    author_if_known: str | None = None
    date_if_known: str | None = None
    confidentiality: PrivateConfidentiality = PrivateConfidentiality.PRIVATE_USER_SOURCE
    provenance: str = "explicit_user_corpus_path"
    ingestion_status: IngestionStatus = IngestionStatus.AUTO_EXTRACTED
    review_status: ReviewStatus = ReviewStatus.REVIEW_REQUIRED
    locator_strategy: str = "section_heading_or_page_locator_required"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.filename.strip() or not self.title.strip():
            raise ValueError("source_id, filename and title are required")
        digest = self.content_hash.lower().strip()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("content_hash must be a SHA-256 hexadecimal digest")
        object.__setattr__(self, "content_hash", digest)
        object.__setattr__(self, "filename", Path(self.filename).name)
        object.__setattr__(
            self,
            "confidentiality",
            self.confidentiality if isinstance(self.confidentiality, PrivateConfidentiality) else PrivateConfidentiality(str(self.confidentiality)),
        )
        object.__setattr__(
            self,
            "ingestion_status",
            self.ingestion_status if isinstance(self.ingestion_status, IngestionStatus) else IngestionStatus(str(self.ingestion_status)),
        )
        object.__setattr__(
            self,
            "review_status",
            self.review_status if isinstance(self.review_status, ReviewStatus) else ReviewStatus(str(self.review_status)),
        )

    @property
    def digest(self) -> str:
        return sha256_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["confidentiality"] = self.confidentiality.value
        data["ingestion_status"] = self.ingestion_status.value
        data["review_status"] = self.review_status.value
        return data


@dataclass(frozen=True)
class PrivateReviewDecision:
    review_id: str
    source_id: str
    item_id: str
    item_type: str
    action: str
    locator: str
    supporting_context: str
    extraction_corruption: bool
    resulting_review_status: ReviewStatus
    reviewer: str
    reviewed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if self.action not in {"VERIFY", "REJECT"}:
            raise ValueError("review action must be VERIFY or REJECT")
        if self.action == "VERIFY" and (not self.locator.strip() or not self.supporting_context.strip()):
            raise ValueError("VERIFIED material requires a locator and readable supporting context")
        if self.action == "VERIFY" and self.extraction_corruption:
            raise ValueError("corrupted extraction cannot be VERIFIED")
        object.__setattr__(
            self,
            "resulting_review_status",
            self.resulting_review_status if isinstance(self.resulting_review_status, ReviewStatus) else ReviewStatus(str(self.resulting_review_status)),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["resulting_review_status"] = self.resulting_review_status.value
        return data


@dataclass(frozen=True)
class SourceConflict:
    conflict_id: str
    source_id_a: str
    source_id_b: str
    differing_fields: tuple[str, ...]
    status: str = "REVIEW_REQUIRED"
    investigation_notes: tuple[str, ...] = ()
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        object.__setattr__(self, "differing_fields", tuple(self.differing_fields))
        object.__setattr__(self, "investigation_notes", tuple(self.investigation_notes))
        if not self.source_id_a.strip() or not self.source_id_b.strip() or not self.differing_fields:
            raise ValueError("source conflict requires both sources and differing fields")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["differing_fields"] = list(self.differing_fields)
        data["investigation_notes"] = list(self.investigation_notes)
        return data


@dataclass(frozen=True)
class PrivateCorpusIngestion:
    source: PrivateSourceRecord
    ingestion: IngestionResult | None
    review_queue: tuple[ReviewItem, ...]
    persisted_metadata_path: str | None = None

    @property
    def candidate_count(self) -> int:
        if self.ingestion is None:
            return 0
        return len(self.ingestion.zettels) + len(self.ingestion.claims) + len(self.ingestion.equations) + len(self.ingestion.entities)

    def to_dict(self) -> dict[str, Any]:
        # Do not serialize private text, sections or candidate summaries here.
        return {
            "source": self.source.to_dict(),
            "review_queue": [item.to_dict() for item in self.review_queue],
            "candidate_count": self.candidate_count,
            "persisted_metadata_path": self.persisted_metadata_path,
        }


class PrivateCorpusService:
    """Explicit-path corpus service with hash, review and conflict gates."""

    TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".csv", ".tsv", ".json"}
    KNOWN_SUFFIXES = TEXT_SUFFIXES | {".pdf", ".docx", ".xlsx", ".xls"}

    def __init__(self, persistence_root: str | Path | None = None):
        self.persistence_root = Path(persistence_root) if persistence_root is not None else None
        if self.persistence_root is not None:
            (self.persistence_root / "private-sources").mkdir(parents=True, exist_ok=True)
            (self.persistence_root / "review-queue").mkdir(parents=True, exist_ok=True)
            (self.persistence_root / "conflicts").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def readiness_status(sources: Iterable[PrivateSourceRecord], reviewed_claims: int = 0) -> CorpusReadinessStatus:
        records = tuple(sources)
        if not records:
            return CorpusReadinessStatus.INFRASTRUCTURE_READY_AWAITING_USER_CORPUS
        if reviewed_claims > 0 and all(record.review_status is ReviewStatus.VERIFIED for record in records):
            return CorpusReadinessStatus.READY_FOR_CORPUS_RESEARCH
        return CorpusReadinessStatus.INGESTED_REVIEW_REQUIRED

    def ingest_text(
        self,
        *,
        source_id: str,
        filename: str,
        title: str,
        text: str,
        source_type: str = "TEXT",
        author_if_known: str | None = None,
        date_if_known: str | None = None,
        confidentiality: PrivateConfidentiality = PrivateConfidentiality.PRIVATE_USER_SOURCE,
        provenance: str = "explicit_user_corpus_text",
    ) -> PrivateCorpusIngestion:
        if not text.strip():
            raise ValueError("corpus text cannot be empty")
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        source = PrivateSourceRecord(
            source_id=source_id,
            filename=filename,
            content_hash=content_hash,
            source_type=source_type,
            title=title,
            author_if_known=author_if_known,
            date_if_known=date_if_known,
            confidentiality=confidentiality,
            provenance=provenance,
        )
        # The existing conservative pipeline returns candidates in memory and
        # marks every candidate REVIEW_REQUIRED.  No source text is persisted.
        public_source = SourceRecord(
            source.source_id,
            source.title,
            authors=tuple(filter(None, (source.author_if_known,))),
            url=None,
            license="USER_PROVIDED_NOT_PUBLIC",
            document_hash=source.content_hash,
            source_type=SourceType.REPORT,
            metadata={"private": True, "filename": source.filename},
        )
        result = KnowledgeIngestionPipeline().ingest(public_source, text)
        self._persist_source(source)
        self._persist_queue(source.source_id, result.review_queue)
        return PrivateCorpusIngestion(source, result, result.review_queue, self._metadata_path(source))

    def ingest_file(
        self,
        path: str | Path,
        *,
        corpus_root: str | Path,
        source_id: str,
        title: str | None = None,
        source_type: str | None = None,
        confidentiality: PrivateConfidentiality = PrivateConfidentiality.PRIVATE_USER_SOURCE,
    ) -> PrivateCorpusIngestion:
        target = self._safe_path(path, corpus_root)
        suffix = target.suffix.lower()
        if suffix not in self.KNOWN_SUFFIXES:
            raise ValueError(f"unsupported corpus file type: {suffix or '<none>'}")
        if suffix not in self.TEXT_SUFFIXES:
            raise ValueError("binary corpus extraction requires an explicit format adapter; no content was read")
        text = target.read_text(encoding="utf-8")
        return self.ingest_text(
            source_id=source_id,
            filename=target.name,
            title=title or target.stem,
            text=text,
            source_type=source_type or suffix.removeprefix(".").upper(),
            confidentiality=confidentiality,
            provenance="explicit_user_corpus_file",
        )

    def review(
        self,
        source: PrivateSourceRecord,
        *,
        item_id: str,
        item_type: str,
        action: str,
        locator: str,
        supporting_context: str,
        extraction_corruption: bool = False,
        reviewer: str = "human_reviewer",
    ) -> PrivateReviewDecision:
        status = ReviewStatus.VERIFIED if action == "VERIFY" else ReviewStatus.REJECTED
        decision = PrivateReviewDecision(
            review_id=f"PRV-{uuid.uuid4().hex[:12].upper()}",
            source_id=source.source_id,
            item_id=item_id,
            item_type=item_type,
            action=action,
            locator=locator,
            supporting_context=supporting_context,
            extraction_corruption=extraction_corruption,
            resulting_review_status=status,
            reviewer=reviewer,
        )
        self._persist_review(decision)
        return decision

    def record_conflict(
        self,
        source_id_a: str,
        source_id_b: str,
        differing_fields: Iterable[str],
        investigation_notes: Iterable[str] = (),
    ) -> SourceConflict:
        conflict = SourceConflict(
            conflict_id=f"CONFLICT-{uuid.uuid4().hex[:12].upper()}",
            source_id_a=source_id_a,
            source_id_b=source_id_b,
            differing_fields=tuple(differing_fields),
            investigation_notes=tuple(investigation_notes),
        )
        if self.persistence_root is not None:
            path = self.persistence_root / "conflicts" / f"{conflict.conflict_id}.json"
            path.write_text(json.dumps(conflict.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return conflict

    @staticmethod
    def _safe_path(path: str | Path, corpus_root: str | Path) -> Path:
        root = Path(corpus_root).resolve()
        if not root.is_dir():
            raise NotADirectoryError(root)
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = root / candidate
        if candidate.is_symlink():
            raise ValueError("corpus path must not be a symlink")
        target = candidate.resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("corpus path must remain inside the explicit corpus root") from exc
        if target == root or not target.is_file() or target.is_symlink():
            raise ValueError("corpus path must be a regular file")
        return target

    def _metadata_path(self, source: PrivateSourceRecord) -> str | None:
        if self.persistence_root is None:
            return None
        return str(self.persistence_root / "private-sources" / f"{source.source_id}.json")

    def _persist_source(self, source: PrivateSourceRecord) -> None:
        if self.persistence_root is None:
            return
        path = self.persistence_root / "private-sources" / f"{source.source_id}.json"
        path.write_text(json.dumps({**source.to_dict(), "digest": source.digest}, indent=2, ensure_ascii=False), encoding="utf-8")

    def _persist_queue(self, source_id: str, items: Iterable[ReviewItem]) -> None:
        if self.persistence_root is None:
            return
        path = self.persistence_root / "review-queue" / f"{source_id}.json"
        path.write_text(json.dumps([item.to_dict() for item in items], indent=2, ensure_ascii=False), encoding="utf-8")

    def _persist_review(self, decision: PrivateReviewDecision) -> None:
        if self.persistence_root is None:
            return
        path = self.persistence_root / "review-queue" / f"{decision.review_id}.decision.json"
        path.write_text(json.dumps(decision.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


__all__ = [
    "CorpusReadinessStatus",
    "PrivateConfidentiality",
    "PrivateCorpusIngestion",
    "PrivateCorpusService",
    "PrivateReviewDecision",
    "PrivateSourceRecord",
    "SourceConflict",
]
