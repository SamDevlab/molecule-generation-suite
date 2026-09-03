"""Versioned provenance records for optional scientific engines.

An engine manifest describes what was available/configured for a run.  It is
deliberately separate from a result: an installed package is not evidence that
an engine was executed, and an executed calculation is not experimental proof.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import os
from typing import Any, Mapping
import uuid

from research_os.core.hashing import sha256_json


class EngineKind(str, Enum):
    DETERMINISTIC_LIBRARY = "DETERMINISTIC_LIBRARY"
    PHYSICS_ENGINE = "PHYSICS_ENGINE"
    COMPUTATIONAL_ENGINE = "COMPUTATIONAL_ENGINE"
    PREPARATION_ENGINE = "PREPARATION_ENGINE"
    MATERIALS_ENGINE = "MATERIALS_ENGINE"


class EngineAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    EXECUTION_FAILED = "EXECUTION_FAILED"


class EngineStatus(str, Enum):
    SUPPORTED_AND_EXECUTED = "SUPPORTED_AND_EXECUTED"
    AVAILABLE_BUT_NOT_EXECUTED = "AVAILABLE_BUT_NOT_EXECUTED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"
    INDETERMINATE = "INDETERMINATE"
    EXECUTION_FAILED = "EXECUTION_FAILED"


class EngineReadiness(str, Enum):
    AVAILABLE = "AVAILABLE"
    CONFIGURED = "CONFIGURED"
    PROTOCOL_READY = "PROTOCOL_READY"
    REFERENCE_VALIDATED = "REFERENCE_VALIDATED"
    NOT_READY = "NOT_READY"


def _value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _normalise_path(value: str | None) -> str | None:
    if not value:
        return None
    return os.path.normpath(str(value))


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): "[REDACTED]" if any(marker in str(key).lower() for marker in ("secret", "token", "password", "api_key")) else _redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


@dataclass(frozen=True)
class EngineManifest:
    engine_id: str
    name: str
    kind: EngineKind | str = EngineKind.COMPUTATIONAL_ENGINE
    version: str | None = None
    availability: EngineAvailability | str = EngineAvailability.UNAVAILABLE
    status: EngineStatus | str = EngineStatus.AVAILABLE_BUT_NOT_EXECUTED
    readiness: EngineReadiness | str = EngineReadiness.NOT_READY
    executable_path: str | None = None
    library_version: str | None = None
    configuration: Mapping[str, Any] = field(default_factory=dict)
    configuration_hash: str | None = None
    protocol_id: str | None = None
    input_hashes: tuple[str, ...] = ()
    output_hashes: tuple[str, ...] = ()
    environment_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    limitations: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    manifest_hash: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "engine_id", str(self.engine_id))
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "kind", _value(self.kind))
        object.__setattr__(self, "availability", _value(self.availability))
        object.__setattr__(self, "status", _value(self.status))
        object.__setattr__(self, "readiness", _value(self.readiness))
        object.__setattr__(self, "executable_path", _normalise_path(self.executable_path))
        object.__setattr__(self, "configuration", _redact(dict(self.configuration or {})))
        object.__setattr__(self, "metadata", _redact(dict(self.metadata or {})))
        object.__setattr__(self, "input_hashes", tuple(str(value) for value in self.input_hashes))
        object.__setattr__(self, "output_hashes", tuple(str(value) for value in self.output_hashes))
        object.__setattr__(self, "limitations", tuple(str(value) for value in self.limitations))
        if self.configuration_hash is None:
            object.__setattr__(self, "configuration_hash", sha256_json(self.configuration))
        if self.manifest_hash is None:
            object.__setattr__(self, "manifest_hash", sha256_json(self._hash_payload()))

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "name": self.name,
            "kind": self.kind,
            "version": self.version,
            "availability": self.availability,
            "status": self.status,
            "readiness": self.readiness,
            "executable_path": self.executable_path,
            "library_version": self.library_version,
            "configuration": self.configuration,
            "configuration_hash": self.configuration_hash,
            "protocol_id": self.protocol_id,
            "input_hashes": self.input_hashes,
            "output_hashes": self.output_hashes,
            "environment_id": self.environment_id,
            "limitations": self.limitations,
            "metadata": self.metadata,
        }

    @property
    def valid(self) -> bool:
        return self.manifest_hash == sha256_json(self._hash_payload()) and self.configuration_hash == sha256_json(self.configuration)

    @property
    def available(self) -> bool:
        return self.availability == EngineAvailability.AVAILABLE.value

    @property
    def configured(self) -> bool:
        return self.readiness in {EngineReadiness.CONFIGURED.value, EngineReadiness.PROTOCOL_READY.value, EngineReadiness.REFERENCE_VALIDATED.value}

    @property
    def reference_validated(self) -> bool:
        return self.readiness == EngineReadiness.REFERENCE_VALIDATED.value

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind
        data["availability"] = self.availability
        data["status"] = self.status
        data["readiness"] = self.readiness
        data["input_hashes"] = list(self.input_hashes)
        data["output_hashes"] = list(self.output_hashes)
        data["limitations"] = list(self.limitations)
        data["configuration"] = dict(self.configuration)
        data["metadata"] = dict(self.metadata)
        return data

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "EngineManifest":
        return cls(
            engine_id=str(raw.get("engine_id") or raw.get("id") or "unknown"),
            name=str(raw.get("name") or raw.get("engine_id") or "unknown"),
            kind=raw.get("kind", EngineKind.COMPUTATIONAL_ENGINE),
            version=raw.get("version"),
            availability=raw.get("availability", EngineAvailability.UNAVAILABLE),
            status=raw.get("status", EngineStatus.AVAILABLE_BUT_NOT_EXECUTED),
            readiness=raw.get("readiness", EngineReadiness.NOT_READY),
            executable_path=raw.get("executable_path"),
            library_version=raw.get("library_version"),
            configuration=raw.get("configuration") or {},
            configuration_hash=raw.get("configuration_hash"),
            protocol_id=raw.get("protocol_id"),
            input_hashes=tuple(raw.get("input_hashes") or ()),
            output_hashes=tuple(raw.get("output_hashes") or ()),
            environment_id=raw.get("environment_id"),
            created_at=str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()),
            limitations=tuple(raw.get("limitations") or ()),
            metadata=raw.get("metadata") or {},
            manifest_hash=raw.get("manifest_hash"),
        )


@dataclass(frozen=True)
class EngineReferenceCase:
    reference_id: str
    engine_id: str
    protocol_id: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    expected_invariants: Mapping[str, Any] = field(default_factory=dict)
    tolerances: Mapping[str, Any] = field(default_factory=dict)
    source: str | None = None
    last_validated_at: str | None = None
    environment_id: str | None = None
    result_status: EngineStatus | str = EngineStatus.AVAILABLE_BUT_NOT_EXECUTED
    run_id: str | None = None
    bundle_id: str | None = None
    result: Mapping[str, Any] = field(default_factory=dict)
    case_hash: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "result_status", _value(self.result_status))
        object.__setattr__(self, "inputs", dict(self.inputs or {}))
        object.__setattr__(self, "expected_invariants", dict(self.expected_invariants or {}))
        object.__setattr__(self, "tolerances", dict(self.tolerances or {}))
        object.__setattr__(self, "result", dict(self.result or {}))
        if self.case_hash is None:
            object.__setattr__(self, "case_hash", sha256_json(self._hash_payload()))

    def _hash_payload(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in ("reference_id", "engine_id", "protocol_id", "inputs", "expected_invariants", "tolerances", "source", "environment_id", "result_status", "run_id", "bundle_id", "result")}

    @property
    def valid(self) -> bool:
        return self.case_hash == sha256_json(self._hash_payload())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["result_status"] = self.result_status
        return data
