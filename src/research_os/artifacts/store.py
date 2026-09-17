"""Small content-addressed artifact store used by ResearchBundle packing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from research_os.core.hashing import sha256_file


class ArtifactStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArtifactRef:
    artifact_hash: str
    stored_path: str
    size: int
    original_path: str | None = None

    @property
    def sha256(self) -> str:
        return self.artifact_hash

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContentAddressedArtifactStore:
    """Store files at ``sha256/<prefix>/<digest>`` and verify on read."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def put_artifact(self, path: str | Path) -> ArtifactRef:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        digest = sha256_file(source)
        destination = self.root / "sha256" / digest[:2] / digest
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_file() and sha256_file(destination) != digest:
            raise ArtifactStoreError(f"content-addressed artifact is corrupted: {destination}")
        if not destination.exists():
            descriptor, temporary_name = tempfile.mkstemp(prefix=f".{digest}.", dir=destination.parent)
            os.close(descriptor)
            temporary = Path(temporary_name)
            try:
                with source.open("rb") as source_handle, temporary.open("wb") as temporary_handle:
                    shutil.copyfileobj(source_handle, temporary_handle)
                    temporary_handle.flush()
                    os.fsync(temporary_handle.fileno())
                if sha256_file(temporary) != digest or temporary.stat().st_size != source.stat().st_size:
                    raise ArtifactStoreError(f"artifact changed while being copied: {source}")
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        return ArtifactRef(digest, str(destination), source.stat().st_size, str(source))

    def get_artifact(self, artifact_hash: str) -> Path:
        self._validate_hash(artifact_hash)
        destination = self.root / "sha256" / artifact_hash[:2] / artifact_hash
        if not destination.is_file():
            raise FileNotFoundError(destination)
        if not self.verify_artifact(artifact_hash):
            raise ArtifactStoreError(f"artifact hash verification failed: {artifact_hash}")
        return destination

    def verify_artifact(self, artifact_hash: str) -> bool:
        try:
            self._validate_hash(artifact_hash)
        except ArtifactStoreError:
            return False
        destination = self.root / "sha256" / artifact_hash[:2] / artifact_hash
        return destination.is_file() and sha256_file(destination) == artifact_hash

    @staticmethod
    def _validate_hash(artifact_hash: str) -> None:
        if not isinstance(artifact_hash, str) or re.fullmatch(r"[0-9a-f]{64}", artifact_hash) is None:
            raise ArtifactStoreError("artifact hash must be a lowercase SHA-256 digest")

    put = put_artifact
    get = get_artifact
    verify = verify_artifact
