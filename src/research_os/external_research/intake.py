"""Canonical, idempotent intake for external research sources.

Registration is deliberately not retrieval.  A source can be registered from
an URI, from a local artifact, or from both.  The local artifact is accepted
only after its content hash is checked; remote failures are represented by a
typed availability code and never substituted silently.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlparse

from research_os.core.hashing import sha256_file, sha256_json
from research_os.knowledge.source import SourceRecord, SourceRegistry, SourceType


class SourceState(str, Enum):
    SOURCE_REGISTERED = "SOURCE_REGISTERED"
    SOURCE_VALID = "SOURCE_VALID"
    SOURCE_INVALID = "SOURCE_INVALID"
    SOURCE_CHANGED = "SOURCE_CHANGED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_NOT_COMPARABLE = "SOURCE_NOT_COMPARABLE"


class SourceAvailabilityCode(str, Enum):
    AVAILABLE = "AVAILABLE"
    LOCAL_ARTIFACT_VALID = "LOCAL_ARTIFACT_VALID"
    LOCAL_ARTIFACT_MISSING = "LOCAL_ARTIFACT_MISSING"
    ARTIFACT_HASH_MISMATCH = "ARTIFACT_HASH_MISMATCH"
    HTTP_403 = "HTTP_403"
    HTTP_404 = "HTTP_404"
    HTTP_429 = "HTTP_429"
    HTTP_5XX = "HTTP_5XX"
    TIMEOUT = "TIMEOUT"
    DNS_FAILURE = "DNS_FAILURE"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


@dataclass(frozen=True)
class SourceAvailability:
    state: SourceState
    code: SourceAvailabilityCode
    detail: str
    http_status: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", self.state if isinstance(self.state, SourceState) else SourceState(str(self.state)))
        object.__setattr__(self, "code", self.code if isinstance(self.code, SourceAvailabilityCode) else SourceAvailabilityCode(str(self.code)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "code": self.code.value,
            "detail": self.detail,
            "http_status": self.http_status,
        }


@dataclass(frozen=True)
class ExternalResearchSource:
    source_id: str
    title: str
    uri: str
    source_type: SourceType | str = SourceType.WEB
    local_path: str | None = None
    expected_sha256: str | None = None
    state: SourceState | str = SourceState.SOURCE_REGISTERED
    availability: SourceAvailability | None = None
    document_sha256: str | None = None
    source_fingerprint: str | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", self.source_id):
            raise ValueError("source_id must be a stable path-safe identifier")
        if not self.title.strip():
            raise ValueError("title is required")
        parsed = urlparse(self.uri)
        if parsed.scheme not in {"http", "https", "file", "doi", "urn"}:
            raise ValueError("uri must use an explicit supported scheme")
        try:
            source_type = self.source_type if isinstance(self.source_type, SourceType) else SourceType(str(self.source_type))
        except ValueError as exc:
            raise ValueError("source_type is not a canonical SourceType") from exc
        object.__setattr__(self, "source_type", source_type)
        object.__setattr__(self, "state", self.state if isinstance(self.state, SourceState) else SourceState(str(self.state)))
        if self.availability is not None and not isinstance(self.availability, SourceAvailability):
            object.__setattr__(self, "availability", SourceAvailability(**dict(self.availability)))
        object.__setattr__(self, "provenance", dict(self.provenance))
        if self.expected_sha256 is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", self.expected_sha256):
            raise ValueError("expected_sha256 must be a SHA-256 hex digest")
        if self.document_sha256 is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", self.document_sha256):
            raise ValueError("document_sha256 must be a SHA-256 hex digest")
        if self.source_fingerprint is None:
            object.__setattr__(self, "source_fingerprint", sha256_json(self._fingerprint_payload()))

    def _fingerprint_payload(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "uri": self.uri,
            "source_type": self.source_type.value,
            "document_sha256": self.document_sha256,
            "provenance": self.provenance,
        }

    @property
    def digest(self) -> str:
        return sha256_json(self.to_dict(include_digest=False))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        data = asdict(self)
        data["source_type"] = self.source_type.value
        data["state"] = self.state.value
        data["provenance"] = dict(self.provenance)
        if self.availability is not None:
            data["availability"] = self.availability.to_dict()
        if include_digest:
            data["digest"] = self.digest
        return data


def classify_remote_outcome(*, http_status: int | None = None, error: str | None = None, comparable: bool = True) -> SourceAvailability:
    """Map retrieval outcomes to stable, non-lossy source states."""

    if not comparable:
        return SourceAvailability(SourceState.SOURCE_NOT_COMPARABLE, SourceAvailabilityCode.NOT_COMPARABLE, "source conditions are not comparable to the target protocol")
    if http_status is not None:
        if http_status == 403:
            return SourceAvailability(SourceState.SOURCE_UNAVAILABLE, SourceAvailabilityCode.HTTP_403, "remote source denied access", http_status)
        if http_status == 404:
            return SourceAvailability(SourceState.SOURCE_UNAVAILABLE, SourceAvailabilityCode.HTTP_404, "remote source was not found", http_status)
        if http_status == 429:
            return SourceAvailability(SourceState.SOURCE_UNAVAILABLE, SourceAvailabilityCode.HTTP_429, "remote source rate-limited the request", http_status)
        if 500 <= http_status <= 599:
            return SourceAvailability(SourceState.SOURCE_UNAVAILABLE, SourceAvailabilityCode.HTTP_5XX, "remote source returned a server error", http_status)
        if 200 <= http_status <= 299:
            return SourceAvailability(SourceState.SOURCE_VALID, SourceAvailabilityCode.AVAILABLE, "remote source responded successfully", http_status)
        return SourceAvailability(SourceState.SOURCE_UNAVAILABLE, SourceAvailabilityCode.INVALID_RESPONSE, "remote source returned an unsupported status", http_status)
    error_text = (error or "").lower()
    if "timeout" in error_text:
        code = SourceAvailabilityCode.TIMEOUT
    elif any(token in error_text for token in ("dns", "name or service", "getaddrinfo")):
        code = SourceAvailabilityCode.DNS_FAILURE
    elif error:
        code = SourceAvailabilityCode.UNKNOWN_FAILURE
    else:
        code = SourceAvailabilityCode.INVALID_RESPONSE
    return SourceAvailability(SourceState.SOURCE_UNAVAILABLE, code, error or "source availability was not established")


class ExternalResearchIntake:
    """Persistent intake facade built on the canonical :class:`SourceRegistry`."""

    def __init__(self, root: str | Path, *, source_registry: SourceRegistry | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.source_registry = source_registry or SourceRegistry(self.root / "source-registry")
        self._records: dict[str, ExternalResearchSource] = {}
        for path in sorted(self.root.glob("*.external-source.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            availability = raw.get("availability")
            item = ExternalResearchSource(
                source_id=raw["source_id"], title=raw["title"], uri=raw["uri"], source_type=raw["source_type"],
                local_path=raw.get("local_path"), expected_sha256=raw.get("expected_sha256"), state=raw["state"],
                availability=SourceAvailability(**availability) if availability else None,
                document_sha256=raw.get("document_sha256"), source_fingerprint=raw.get("source_fingerprint"),
                provenance=raw.get("provenance") or {}, registered_at=raw.get("registered_at") or datetime.now(timezone.utc).isoformat(),
            )
            if raw.get("digest") and raw["digest"] != item.digest:
                raise ValueError(f"external source manifest digest mismatch: {path.name}")
            self._records[item.source_id] = item

    def get(self, source_id: str) -> ExternalResearchSource:
        try:
            return self._records[source_id]
        except KeyError as exc:
            raise KeyError(f"external source not registered: {source_id}") from exc

    def list(self) -> tuple[ExternalResearchSource, ...]:
        return tuple(self._records.values())

    def register(self, *, source_id: str, title: str, uri: str, source_type: SourceType | str = SourceType.WEB, local_path: str | Path | None = None, expected_sha256: str | None = None, provenance: Mapping[str, Any] | None = None) -> ExternalResearchSource:
        path = Path(local_path) if local_path is not None else None
        document_hash = sha256_file(path) if path is not None and path.is_file() else None
        if path is not None and not path.is_file():
            availability = SourceAvailability(SourceState.SOURCE_UNAVAILABLE, SourceAvailabilityCode.LOCAL_ARTIFACT_MISSING, "declared local artifact does not exist")
            state = SourceState.SOURCE_UNAVAILABLE
        elif path is not None and expected_sha256 and document_hash != expected_sha256:
            availability = SourceAvailability(SourceState.SOURCE_INVALID, SourceAvailabilityCode.ARTIFACT_HASH_MISMATCH, "local artifact hash does not match the declared fingerprint")
            state = SourceState.SOURCE_INVALID
        elif path is not None:
            availability = SourceAvailability(SourceState.SOURCE_VALID, SourceAvailabilityCode.LOCAL_ARTIFACT_VALID, "local artifact hash verified")
            state = SourceState.SOURCE_VALID
        else:
            availability = None
            state = SourceState.SOURCE_REGISTERED
        item = ExternalResearchSource(source_id, title, uri, source_type, str(path) if path is not None else None, expected_sha256, state, availability, document_hash, None, provenance or {})
        existing = self._records.get(source_id)
        if existing is not None:
            if existing.source_fingerprint == item.source_fingerprint and existing.document_sha256 == item.document_sha256:
                return existing
            changed = ExternalResearchSource(**{**item.to_dict(include_digest=False), "state": SourceState.SOURCE_CHANGED, "availability": SourceAvailability(SourceState.SOURCE_CHANGED, SourceAvailabilityCode.INVALID_RESPONSE, "source identity or artifact fingerprint changed")})
            self._persist(changed)
            self._records[source_id] = changed
            return changed
        record = SourceRecord(source_id=source_id, title=title, url=uri, document_hash=document_hash, source_type=source_type, metadata={"external_research": True, "local_path": str(path) if path else None, "source_fingerprint": item.source_fingerprint, "provenance": dict(provenance or {})})
        try:
            self.source_registry.register(record)
        except ValueError:
            registered = self.source_registry.get(source_id)
            if registered.document_hash != document_hash or registered.url != uri:
                changed = ExternalResearchSource(**{**item.to_dict(include_digest=False), "state": SourceState.SOURCE_CHANGED, "availability": SourceAvailability(SourceState.SOURCE_CHANGED, SourceAvailabilityCode.INVALID_RESPONSE, "canonical SourceRegistry record conflicts with intake")})
                self._persist(changed)
                self._records[source_id] = changed
                return changed
        self._persist(item)
        self._records[source_id] = item
        return item

    def assess_remote(self, source_id: str, *, http_status: int | None = None, error: str | None = None, comparable: bool = True) -> ExternalResearchSource:
        current = self.get(source_id)
        availability = classify_remote_outcome(http_status=http_status, error=error, comparable=comparable)
        item = ExternalResearchSource(**{**current.to_dict(include_digest=False), "state": availability.state, "availability": availability})
        self._persist(item)
        self._records[source_id] = item
        return item

    def verify_local_artifact(self, source_id: str, path: str | Path | None = None) -> ExternalResearchSource:
        current = self.get(source_id)
        target = Path(path or current.local_path or "")
        if not target.is_file():
            availability = SourceAvailability(SourceState.SOURCE_UNAVAILABLE, SourceAvailabilityCode.LOCAL_ARTIFACT_MISSING, "local artifact does not exist")
            item = ExternalResearchSource(**{**current.to_dict(include_digest=False), "state": availability.state, "availability": availability})
        else:
            digest = sha256_file(target)
            if current.expected_sha256 and digest != current.expected_sha256:
                availability = SourceAvailability(SourceState.SOURCE_INVALID, SourceAvailabilityCode.ARTIFACT_HASH_MISMATCH, "local artifact hash does not match the declared fingerprint")
                item = ExternalResearchSource(**{**current.to_dict(include_digest=False), "local_path": str(target), "document_sha256": digest, "state": availability.state, "availability": availability})
            else:
                availability = SourceAvailability(SourceState.SOURCE_VALID, SourceAvailabilityCode.LOCAL_ARTIFACT_VALID, "local artifact hash verified")
                item = ExternalResearchSource(**{**current.to_dict(include_digest=False), "local_path": str(target), "document_sha256": digest, "state": availability.state, "availability": availability})
        self._persist(item)
        self._records[source_id] = item
        return item

    def _persist(self, item: ExternalResearchSource) -> None:
        target = self.root / f"{item.source_id}.external-source.json"
        target.write_text(json.dumps(item.to_dict(), indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
