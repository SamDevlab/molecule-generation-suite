"""Fail-closed engine adapter registration and execution preflight."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from .manifest import EngineAvailability, EngineManifest
from .registry import EngineRegistry


class EnginePreflightStatus(str, Enum):
    ENGINE_AVAILABLE = "ENGINE_AVAILABLE"
    ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"
    ENGINE_VERSION_MISMATCH = "ENGINE_VERSION_MISMATCH"
    ENGINE_INPUT_UNSUPPORTED = "ENGINE_INPUT_UNSUPPORTED"
    ENGINE_EXECUTION_FAILED = "ENGINE_EXECUTION_FAILED"
    ENGINE_TIMEOUT = "ENGINE_TIMEOUT"
    ENGINE_OUTPUT_INVALID = "ENGINE_OUTPUT_INVALID"
    NOT_REGISTERED = "NOT_REGISTERED"
    INVALID_MANIFEST = "INVALID_MANIFEST"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    # Compatibility aliases for callers that used the initial preflight API.
    READY = "ENGINE_AVAILABLE"
    UNAVAILABLE = "ENGINE_UNAVAILABLE"


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
        return self.status == EnginePreflightStatus.ENGINE_AVAILABLE

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

    registry.register_adapter("autodock-vina", adapter_name="VinaEngine", capabilities=("docking", "version_probe", "argv_execution"), supported_inputs=("pdbqt",), supported_outputs=("pdbqt", "log"), factory=lambda manifest: VinaEngine(manifest.executable_path))
    registry.register_adapter("openbabel", adapter_name="OpenBabelEngine", capabilities=("structure_preparation", "conversion", "version_probe", "argv_execution"), supported_inputs=("pdb", "sdf", "mol", "smi"), supported_outputs=("pdbqt", "pdb", "sdf"), factory=lambda manifest: OpenBabelEngine(manifest.executable_path))


class EnginePreflight:
    def __init__(self, registry: EngineRegistry):
        self.registry = registry

    def check(self, engine_id: str, *, required_capability: str | None = None, expected_version: str | None = None, input_kind: str | None = None) -> EnginePreflightResult:
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
        if input_kind and input_kind not in registration.supported_inputs:
            return EnginePreflightResult(key, EnginePreflightStatus.ENGINE_INPUT_UNSUPPORTED, manifest, registration.adapter_name, registration.capabilities, "ENGINE_INPUT_UNSUPPORTED", {"input_kind": input_kind, "supported_inputs": list(registration.supported_inputs)})
        if expected_version and manifest.version != expected_version:
            return EnginePreflightResult(key, EnginePreflightStatus.ENGINE_VERSION_MISMATCH, manifest, registration.adapter_name, registration.capabilities, "ENGINE_VERSION_MISMATCH", {"expected_version": expected_version, "detected_version": manifest.version})
        if manifest.availability == EngineAvailability.NOT_CONFIGURED.value:
            return EnginePreflightResult(key, EnginePreflightStatus.ENGINE_UNAVAILABLE, manifest, registration.adapter_name, registration.capabilities, "ENGINE_NOT_CONFIGURED")
        if not manifest.available:
            return EnginePreflightResult(key, EnginePreflightStatus.ENGINE_UNAVAILABLE, manifest, registration.adapter_name, registration.capabilities, "ENGINE_UNAVAILABLE", {"version": manifest.version})
        try:
            adapter = self.registry.create_adapter(key)
            available = bool(getattr(adapter, "available", False))
        except Exception as exc:
            return EnginePreflightResult(key, EnginePreflightStatus.ENGINE_UNAVAILABLE, manifest, registration.adapter_name, registration.capabilities, "ADAPTER_CONSTRUCTION_FAILED", {"error_type": type(exc).__name__})
        if not available:
            return EnginePreflightResult(key, EnginePreflightStatus.ENGINE_UNAVAILABLE, manifest, registration.adapter_name, registration.capabilities, "ADAPTER_REPORTS_UNAVAILABLE")
        return EnginePreflightResult(key, EnginePreflightStatus.ENGINE_AVAILABLE, manifest, registration.adapter_name, registration.capabilities, diagnostics={"version": manifest.version, "executable": manifest.executable_path, "invocation": "argv; shell=False"})

    def check_many(self, engine_ids: Iterable[str]) -> tuple[EnginePreflightResult, ...]:
        return tuple(self.check(engine_id) for engine_id in engine_ids)

    def require_all(self, engine_ids: Iterable[str]) -> tuple[EnginePreflightResult, ...]:
        results = self.check_many(engine_ids)
        if not all(item.can_execute for item in results):
            raise RuntimeError("ENGINE_PREFLIGHT_FAILED: " + ", ".join(f"{item.engine_id}:{item.reason_code}" for item in results if not item.can_execute))
        return results

    @staticmethod
    def classify_execution(result: Any) -> EnginePreflightStatus:
        if bool(getattr(result, "timed_out", False)):
            return EnginePreflightStatus.ENGINE_TIMEOUT
        if int(getattr(result, "returncode", 1)) != 0:
            return EnginePreflightStatus.ENGINE_EXECUTION_FAILED
        output_path = getattr(result, "output_path", None)
        if output_path is not None and not Path(str(output_path)).is_file():
            return EnginePreflightStatus.ENGINE_OUTPUT_INVALID
        return EnginePreflightStatus.ENGINE_AVAILABLE
