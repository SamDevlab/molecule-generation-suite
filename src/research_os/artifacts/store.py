"""Small content-addressed artifact store used by ResearchBundle packing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
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
            destination.write_bytes(source.read_bytes())
        return ArtifactRef(digest, str(destination), source.stat().st_size, str(source))

    def get_artifact(self, artifact_hash: str) -> Path:
        destination = self.root / "sha256" / artifact_hash[:2] / artifact_hash
        if not destination.is_file():
            raise FileNotFoundError(destination)
        if not self.verify_artifact(artifact_hash):
            raise ArtifactStoreError(f"artifact hash verification failed: {artifact_hash}")
        return destination

    def verify_artifact(self, artifact_hash: str) -> bool:
        destination = self.root / "sha256" / artifact_hash[:2] / artifact_hash
        return destination.is_file() and sha256_file(destination) == artifact_hash

    put = put_artifact
    get = get_artifact
    verify = verify_artifact
