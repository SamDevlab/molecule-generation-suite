"""Fail-closed engine adapter registration and execution preflight."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable

from .manifest import EngineAvailability, EngineManifest
from .registry import EngineRegistry


class EnginePreflightStatus(str, Enum):
    READY = "READY"
    NOT_REGISTERED = "NOT_REGISTERED"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID_MANIFEST = "INVALID_MANIFEST"
    NOT_CONFIGURED = "NOT_CONFIGURED"


@dataclass(frozen=True)
class EnginePreflightResult:
    engine_id: str
    status: EnginePreflightStatus
    manifest: EngineManifest | None
    adapter_name: str | None
    capabilities: tuple[str, ...] = ()
    reason_code: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def can_execute(self) -> bool:
        return self.status == EnginePreflightStatus.READY

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["capabilities"] = list(self.capabilities)
        if self.manifest is not None:
            data["manifest"] = self.manifest.to_dict()
        return data


def register_external_research_adapters(registry: EngineRegistry) -> None:
    """Register only the two adapters required by the cross-structure run."""

    from .openbabel import OpenBabelEngine
    from .vina import VinaEngine

    registry.register_adapter("autodock-vina", adapter_name="VinaEngine", capabilities=("docking", "version_probe", "argv_execution"), factory=lambda manifest: VinaEngine(manifest.executable_path))
    registry.register_adapter("openbabel", adapter_name="OpenBabelEngine", capabilities=("structure_preparation", "conversion", "version_probe", "argv_execution"), factory=lambda manifest: OpenBabelEngine(manifest.executable_path))


class EnginePreflight:
    def __init__(self, registry: EngineRegistry):
        self.registry = registry

    def check(self, engine_id: str, *, required_capability: str | None = None) -> EnginePreflightResult:
        key = self.registry._alias(engine_id)
        try:
            registration = self.registry.adapter_registration(key)
        except KeyError:
            return EnginePreflightResult(key, EnginePreflightStatus.NOT_REGISTERED, None, None, reason_code="ADAPTER_NOT_REGISTERED")
        manifest = self.registry.get_engine(key)
        if not manifest.valid:
            return EnginePreflightResult(key, EnginePreflightStatus.INVALID_MANIFEST, manifest, registration.adapter_name, registration.capabilities, "MANIFEST_HASH_INVALID")
        if required_capability and required_capability not in registration.capabilities:
            return EnginePreflightResult(key, EnginePreflightStatus.NOT_CONFIGURED, manifest, registration.adapter_name, registration.capabilities, "CAPABILITY_NOT_REGISTERED", {"required_capability": required_capability})
        if manifest.availability == EngineAvailability.NOT_CONFIGURED.value:
            return EnginePreflightResult(key, EnginePreflightStatus.NOT_CONFIGURED, manifest, registration.adapter_name, registration.capabilities, "ENGINE_NOT_CONFIGURED")
        if not manifest.available:
            return EnginePreflightResult(key, EnginePreflightStatus.UNAVAILABLE, manifest, registration.adapter_name, registration.capabilities, "ENGINE_UNAVAILABLE", {"version": manifest.version})
        try:
            adapter = self.registry.create_adapter(key)
            available = bool(getattr(adapter, "available", False))
        except Exception as exc:
            return EnginePreflightResult(key, EnginePreflightStatus.UNAVAILABLE, manifest, registration.adapter_name, registration.capabilities, "ADAPTER_CONSTRUCTION_FAILED", {"error_type": type(exc).__name__})
        if not available:
            return EnginePreflightResult(key, EnginePreflightStatus.UNAVAILABLE, manifest, registration.adapter_name, registration.capabilities, "ADAPTER_REPORTS_UNAVAILABLE")
        return EnginePreflightResult(key, EnginePreflightStatus.READY, manifest, registration.adapter_name, registration.capabilities, diagnostics={"version": manifest.version, "executable": manifest.executable_path})

    def check_many(self, engine_ids: Iterable[str]) -> tuple[EnginePreflightResult, ...]:
        return tuple(self.check(engine_id) for engine_id in engine_ids)

    def require_all(self, engine_ids: Iterable[str]) -> tuple[EnginePreflightResult, ...]:
        results = self.check_many(engine_ids)
        if not all(item.can_execute for item in results):
            raise RuntimeError("ENGINE_PREFLIGHT_FAILED: " + ", ".join(f"{item.engine_id}:{item.reason_code}" for item in results if not item.can_execute))
        return results
