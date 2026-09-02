from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import uuid
from typing import Any, Mapping

from research_os.core.hashing import sha256_json


@dataclass(frozen=True)
class DependencyInfo:
    available: bool
    version: str | None = None


EngineInfo = DependencyInfo


class _FrozenDict(dict[str, Any]):
    def _blocked(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("environment manifest mappings are immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = _blocked


def _mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return _FrozenDict(dict(value or {}))


@dataclass(frozen=True)
class EnvironmentManifest:
    environment_id: str = field(default_factory=lambda: f"ENV-{uuid.uuid4().hex[:12].upper()}")
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    python: dict[str, Any] = field(default_factory=dict)
    platform: dict[str, Any] = field(default_factory=dict)
    git: dict[str, Any] = field(default_factory=dict)
    dependencies: dict[str, DependencyInfo] = field(default_factory=dict)
    engines: dict[str, DependencyInfo] = field(default_factory=dict)
    environment_hash: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "python", _mapping(self.python))
        object.__setattr__(self, "platform", _mapping(self.platform))
        object.__setattr__(self, "git", _mapping(self.git))
        object.__setattr__(self, "dependencies", _FrozenDict({str(name): _dependency(value) for name, value in self.dependencies.items()}))
        object.__setattr__(self, "engines", _FrozenDict({str(name): _dependency(value) for name, value in self.engines.items()}))
        if self.environment_hash is None:
            object.__setattr__(self, "environment_hash", sha256_json(self._hash_payload()))

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "python": self.python,
            "platform": self.platform,
            "git": self.git,
            "dependencies": {key: asdict(value) for key, value in sorted(self.dependencies.items())},
            "engines": {key: asdict(value) for key, value in sorted(self.engines.items())},
        }

    @property
    def computed_hash(self) -> str:
        return sha256_json(self._hash_payload())

    @property
    def valid(self) -> bool:
        return self.environment_hash == self.computed_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "created_at": self.created_at,
            "python": dict(self.python),
            "platform": dict(self.platform),
            "git": dict(self.git),
            "dependencies": {key: asdict(value) for key, value in sorted(self.dependencies.items())},
            "engines": {key: asdict(value) for key, value in sorted(self.engines.items())},
            "environment_hash": self.environment_hash,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "EnvironmentManifest":
        return cls(
            environment_id=str(raw.get("environment_id") or f"ENV-{uuid.uuid4().hex[:12].upper()}"),
            created_at=str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()),
            python=_mapping(raw.get("python")),
            platform=_mapping(raw.get("platform")),
            git=_mapping(raw.get("git")),
            dependencies={str(key): _dependency(value) for key, value in _mapping(raw.get("dependencies")).items()},
            engines={str(key): _dependency(value) for key, value in _mapping(raw.get("engines")).items()},
            environment_hash=raw.get("environment_hash"),
        )


def _dependency(value: Any) -> DependencyInfo:
    if isinstance(value, DependencyInfo):
        return value
    if isinstance(value, Mapping):
        return DependencyInfo(bool(value.get("available", False)), value.get("version"))
    return DependencyInfo(bool(value), None)
