"""Protocol-aware cache keys; cache reuse is never implicit across protocols."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from research_os.core.hashing import sha256_json


@dataclass(frozen=True)
class CacheKey:
    input_hash: str
    config_hash: str
    code_commit: str
    engine_version: str
    protocol_version: str

    @property
    def digest(self) -> str:
        return sha256_json(asdict(self))

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "digest": self.digest}


class ResearchCache:
    def __init__(self):
        self._values: dict[str, Any] = {}

    def get(self, key: CacheKey) -> Any | None:
        return self._values.get(key.digest)

    def put(self, key: CacheKey, value: Any) -> str:
        self._values[key.digest] = value
        return key.digest

    def contains(self, key: CacheKey) -> bool:
        return key.digest in self._values

