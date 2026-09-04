"""Conservative source-to-review ingestion pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import re
import uuid
from typing import Any

from research_os.core.hashing import sha256_json
from research_os.core.types import EvidenceLevel
from research_os.knowledge.equations import EquationRecord
from research_os.knowledge.source import SourceRecord
from research_os.knowledge.zettel import ReviewStatus, SourceLocator, Zettel, ZettelType


class IngestionStatus(str, Enum):
    AUTO_EXTRACTED = "AUTO_EXTRACTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    source_id: str
    title: str
    document_hash: str
    sections: tuple[dict[str, Any], ...] = ()
    status: IngestionStatus = IngestionStatus.AUTO_EXTRACTED

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["sections"] = [dict(section) for section in self.sections]
        data["status"] = self.status.value
        return data


@dataclass(frozen=True)
class ReviewItem:
    review_id: str
    item_type: str
    item_id: str
    status: IngestionStatus
    source_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass(frozen=True)
class IngestionResult:
    document: DocumentRecord
    zettels: tuple[Zettel, ...] = ()
    claims: tuple[dict[str, Any], ...] = ()
    equations: tuple[EquationRecord, ...] = ()
    entities: tuple[dict[str, Any], ...] = ()
    review_queue: tuple[ReviewItem, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": self.document.to_dict(),
            "zettels": [item.to_dict() for item in self.zettels],
            "claims": [dict(item) for item in self.claims],
            "equations": [item.to_dict() for item in self.equations],
            "entities": [dict(item) for item in self.entities],
            "review_queue": [item.to_dict() for item in self.review_queue],
        }


class KnowledgeIngestionPipeline:
    """Extract candidates, never silently verifies AI-produced material."""

    def ingest(self, source: SourceRecord, text: str) -> IngestionResult:
        if not text.strip():
            raise ValueError("document text cannot be empty")
        sections = self._sections(text)
        document = DocumentRecord(f"DOC-{uuid.uuid4().hex[:12].upper()}", source.source_id, source.title, sha256_json({"source_id": source.source_id, "text": text}), tuple(sections))
        locators = (SourceLocator(source.source_id, url=source.url, doi=source.doi),)
        zettels: list[Zettel] = []
        claims: list[dict[str, Any]] = []
        equations: list[EquationRecord] = []
        entities: list[dict[str, Any]] = []
        for section in sections:
            heading = section["heading"]
            body = section["text"]
            zettel = Zettel(title=heading, summary=body[:2000], zettel_type=ZettelType.CONCEPT, domain="UNSPECIFIED", evidence_level=EvidenceLevel.E0_HEURISTIC, review_status=ReviewStatus.REVIEW_REQUIRED, sources=locators)
            zettels.append(zettel)
            claims.append({"claim_id": f"CLM-{uuid.uuid4().hex[:12].upper()}", "statement": body[:500], "source_id": source.source_id, "locator": heading, "review_status": IngestionStatus.REVIEW_REQUIRED.value})
            for expression in re.findall(r"[^\n]*[=≈]\s*[^\n]+", body):
                equations.append(EquationRecord(f"EQ-{uuid.uuid4().hex[:12].upper()}", expression.strip(), (), {}, source_id=source.source_id, locator=heading, review_status=IngestionStatus.REVIEW_REQUIRED.value))
            for entity in re.findall(r"\b[A-Z][A-Za-z0-9_-]{2,}\b", body):
                entities.append({"entity_id": f"ENT-{uuid.uuid4().hex[:12].upper()}", "name": entity, "source_id": source.source_id, "locator": heading, "review_status": IngestionStatus.REVIEW_REQUIRED.value})
        review = tuple(ReviewItem(f"REV-{uuid.uuid4().hex[:12].upper()}", kind, item_id, IngestionStatus.REVIEW_REQUIRED, source.source_id, "auto-extracted material requires human review before VERIFIED") for kind, ids in (("zettel", [item.zettel_id for item in zettels]), ("claim", [item["claim_id"] for item in claims]), ("equation", [item.equation_id for item in equations]), ("entity", [item["entity_id"] for item in entities])) for item_id in ids)
        return IngestionResult(document, tuple(zettels), tuple(claims), tuple(equations), tuple(entities), review)

    @staticmethod
    def _sections(text: str) -> list[dict[str, Any]]:
        matches = list(re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*$", text))
        if not matches:
            return [{"heading": "Document", "text": text.strip()}]
        sections = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[match.end():end].strip()
            if body:
                sections.append({"heading": match.group(1).strip(), "text": body})
        return sections
