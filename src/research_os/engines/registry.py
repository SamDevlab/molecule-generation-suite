"""Safe discovery and persistence helpers for Research OS engines."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from importlib import metadata
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping

from research_os.engines.manifest import (
    EngineAvailability,
    EngineKind,
    EngineManifest,
    EngineReadiness,
    EngineStatus,
)


@dataclass(frozen=True)
class EngineSpec:
    engine_id: str
    name: str
    kind: EngineKind
    module: str | None = None
    executable_names: tuple[str, ...] = ()
    version_args: tuple[str, ...] = ()


DEFAULT_ENGINE_SPECS = (
    EngineSpec("rdkit", "RDKit", EngineKind.DETERMINISTIC_LIBRARY, "rdkit"),
    EngineSpec("cantera", "Cantera", EngineKind.PHYSICS_ENGINE, "cantera"),
    EngineSpec("openbabel", "Open Babel", EngineKind.PREPARATION_ENGINE, None, ("obabel", "obabel.exe"), ("-V",)),
    EngineSpec("autodock-vina", "AutoDock Vina", EngineKind.COMPUTATIONAL_ENGINE, None, ("vina", "vina.exe"), ("--version",)),
    EngineSpec("pymatgen", "pymatgen", EngineKind.MATERIALS_ENGINE, "pymatgen"),
    EngineSpec("matminer", "matminer", EngineKind.MATERIALS_ENGINE, "matminer"),
    EngineSpec("pycalphad", "pycalphad", EngineKind.PHYSICS_ENGINE, "pycalphad"),
)


def _module_version(module: Any, package: str) -> str | None:
    value = getattr(module, "__version__", None)
    if value is None:
        try:
            value = metadata.version(package)
        except metadata.PackageNotFoundError:
            value = None
    return str(value) if value is not None else None


class EngineRegistry:
    """Registry whose probes only import modules or run version argv."""

    def __init__(self, root: str | Path | None = None, *, environment_id: str | None = None, specs=DEFAULT_ENGINE_SPECS, configuration: Mapping[str, Mapping[str, Any]] | None = None):
        self.root = Path(root) if root is not None else None
        self.environment_id = environment_id
        self.specs = tuple(specs)
        self.configuration = {str(key): dict(value) for key, value in (configuration or {}).items()}
        self._manifests: dict[str, EngineManifest] = {}

    def register_engine(self, manifest: EngineManifest | Mapping[str, Any]) -> EngineManifest:
        item = manifest if isinstance(manifest, EngineManifest) else EngineManifest.from_mapping(manifest)
        self._manifests[item.engine_id] = item
        return item

    def get_engine(self, engine_id: str) -> EngineManifest:
        key = self._alias(engine_id)
        if key not in self._manifests:
            self.probe_engine(key)
        return self._manifests[key]

    def list_engines(self) -> list[EngineManifest]:
        for spec in self.specs:
            if spec.engine_id not in self._manifests:
                self.probe_engine(spec.engine_id)
        return [self._manifests[spec.engine_id] for spec in self.specs]

    def probe_all(self) -> list[EngineManifest]:
        result = self.list_engines()
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)
            (self.root / "manifests.json").write_text(json.dumps([item.to_dict() for item in result], indent=2, sort_keys=True), encoding="utf-8")
        return result

    def probe_engine(self, engine_id: str) -> EngineManifest:
        key = self._alias(engine_id)
        spec = next((item for item in self.specs if item.engine_id == key), None)
        if spec is None:
            raise KeyError(f"unknown engine: {engine_id}")
        config = self.configuration.get(key, {})
        version = None
        executable = None
        availability = EngineAvailability.UNAVAILABLE
        status = EngineStatus.UNAVAILABLE
        readiness = EngineReadiness.NOT_READY
        limitation = "availability probe did not execute a scientific reference case"
        if spec.module:
            try:
                module = import_module(spec.module)
            except (ImportError, ModuleNotFoundError):
                pass
            else:
                version = _module_version(module, spec.module)
                availability = EngineAvailability.AVAILABLE
                status = EngineStatus.AVAILABLE_BUT_NOT_EXECUTED
                readiness = EngineReadiness.AVAILABLE
                database = config.get("database")
                if database is not None:
                    if Path(str(database)).is_file():
                        readiness = EngineReadiness.CONFIGURED
                    else:
                        status = EngineStatus.NOT_CONFIGURED
                        readiness = EngineReadiness.AVAILABLE
        else:
            configured_path = config.get("executable")
            executable = str(configured_path) if configured_path else None
            if executable:
                path = Path(executable)
                if not path.is_file():
                    status = EngineStatus.UNAVAILABLE
                else:
                    executable = str(path)
            else:
                executable = next((shutil.which(name) for name in spec.executable_names if shutil.which(name)), None)
                if executable is None:
                    availability = EngineAvailability.NOT_CONFIGURED
                    status = EngineStatus.NOT_CONFIGURED
            if executable and Path(executable).is_file():
                try:
                    proc = subprocess.run([executable, *spec.version_args], capture_output=True, text=True, timeout=10, check=False, shell=False)
                except (OSError, subprocess.SubprocessError):
                    status = EngineStatus.UNAVAILABLE
                else:
                    version_text = (proc.stdout or proc.stderr).strip().splitlines()
                    version = version_text[0] if version_text else None
                    availability = EngineAvailability.AVAILABLE if proc.returncode == 0 else EngineAvailability.UNAVAILABLE
                    status = EngineStatus.AVAILABLE_BUT_NOT_EXECUTED if availability == EngineAvailability.AVAILABLE else EngineStatus.UNAVAILABLE
                    readiness = EngineReadiness.CONFIGURED if availability == EngineAvailability.AVAILABLE else EngineReadiness.NOT_READY
        if availability == EngineAvailability.AVAILABLE and readiness == EngineReadiness.NOT_READY:
            readiness = EngineReadiness.AVAILABLE
        manifest = EngineManifest(
            engine_id=key,
            name=spec.name,
            kind=spec.kind,
            version=version,
            library_version=version if spec.module else None,
            availability=availability,
            status=status,
            readiness=readiness,
            executable_path=executable,
            configuration=config,
            environment_id=self.environment_id,
            limitations=(limitation,),
            metadata={"probe": "import_or_version_argv", "configured": bool(config)},
        )
        self._manifests[key] = manifest
        return manifest

    def capture_manifest(self, engine_id: str) -> EngineManifest:
        return self.probe_engine(engine_id)

    @staticmethod
    def verify_engine(manifest: EngineManifest | Mapping[str, Any]) -> bool:
        item = manifest if isinstance(manifest, EngineManifest) else EngineManifest.from_mapping(manifest)
        return item.valid

    @staticmethod
    def _alias(engine_id: str) -> str:
        return {"vina": "autodock-vina", "autodock_vina": "autodock-vina", "obabel": "openbabel"}.get(str(engine_id), str(engine_id))
