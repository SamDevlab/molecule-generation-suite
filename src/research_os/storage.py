"""Persistence and artifact backend interfaces without premature rewrites."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from research_os.artifacts.store import ArtifactRef, ContentAddressedArtifactStore


class PersistenceBackend(Protocol):
    def save(self, key: str, value: dict[str, Any]) -> None: ...
    def load(self, key: str) -> dict[str, Any] | None: ...


class ArtifactBackend(Protocol):
    def put(self, path: str | Path) -> ArtifactRef: ...
    def get(self, artifact_hash: str) -> Path: ...
    def verify(self, artifact_hash: str) -> bool: ...


class FilesystemArtifactBackend(ContentAddressedArtifactStore):
    """Current filesystem implementation behind the future object-store API."""


class InMemoryPersistence:
    def __init__(self):
        self._values: dict[str, dict[str, Any]] = {}

    def save(self, key: str, value: dict[str, Any]) -> None:
        self._values[key] = dict(value)

    def load(self, key: str) -> dict[str, Any] | None:
        value = self._values.get(key)
        return dict(value) if value is not None else None

