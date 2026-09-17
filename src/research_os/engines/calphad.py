from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol
from research_os.core.hashing import sha256_file, sha256_json

@dataclass(frozen=True)
class CalphadRequest:
    composition: dict[str, float]
    fraction_basis: str
    temperature_k: float | None = None
    pressure_pa: float = 101325.0
    database: str | None = None
    phases: tuple[str, ...] = ()
    database_id: str | None = None
    database_source: str | None = None
    database_license: str | None = None

@dataclass(frozen=True)
class CalphadResult:
    engine: str
    engine_version: str | None
    database: str
    temperature_k: float | None
    pressure_pa: float
    phase_fractions: dict[str, float]
    outputs: dict[str, Any]
    model: str = "CALPHAD_equilibrium"
    database_sha256: str | None = None
    database_manifest: dict[str, Any] | None = None
    status: str = "SUPPORTED_AND_EXECUTED"
    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class CalphadDatabaseManifest:
    database_id: str
    source: str
    sha256: str
    license: str | None = None
    manifest_hash: str | None = None

    def __post_init__(self) -> None:
        if self.manifest_hash is None:
            object.__setattr__(self, "manifest_hash", sha256_json({"database_id": self.database_id, "source": self.source, "sha256": self.sha256, "license": self.license}))

    def to_dict(self) -> dict[str, Any]: return asdict(self)


DatabaseManifest = CalphadDatabaseManifest

class CalphadEngine(Protocol):
    @property
    def available(self) -> bool: ...
    @property
    def version(self) -> str | None: ...
    def calculate(self, request: CalphadRequest) -> CalphadResult: ...

class UnavailableCalphadEngine:
    """Fail-closed placeholder until an appropriate thermodynamic DB is configured."""
    available=False; version=None
    def calculate(self, request: CalphadRequest) -> CalphadResult: raise RuntimeError("no CALPHAD engine/database configured")


class CalphadDatabaseUnavailableError(RuntimeError):
    pass


class PyCalphadEngine:
    """Real pycalphad adapter. A TDB path is mandatory; no implicit database."""
    def __init__(self, database: str | Path | None = None):
        self.database = str(database) if database is not None else None
        try:
            import pycalphad  # type: ignore[import-not-found]
        except ImportError:
            self._module = None
        else:
            self._module = pycalphad
    @property
    def available(self) -> bool: return self._module is not None
    @property
    def version(self) -> str | None: return getattr(self._module, "__version__", None) if self._module is not None else None
    def database_manifest(self, request: CalphadRequest) -> CalphadDatabaseManifest:
        path = request.database or self.database
        if not path or not Path(path).is_file():
            raise CalphadDatabaseUnavailableError(f"CALPHAD database is not configured or missing: {path or '<none>'}")
        return CalphadDatabaseManifest(request.database_id or Path(path).stem, str(Path(path).resolve()), sha256_file(path), request.database_license)
    def calculate(self, request: CalphadRequest) -> CalphadResult:
        if not self.available: raise RuntimeError("pycalphad is not installed")
        manifest = self.database_manifest(request)
        from pycalphad import Database, equilibrium, variables as v  # type: ignore[import-not-found]
        dbf = Database(manifest.source)
        components = sorted(request.composition)
        phases = list(request.phases) or list(dbf.phases)
        condition = {v.T: request.temperature_k or 1000.0, v.P: request.pressure_pa}
        result = equilibrium(dbf, components, phases, condition)
        phase_fractions: dict[str, float] = {}
        phase_values = getattr(getattr(result, "Phase", None), "values", ())
        np_values = getattr(getattr(result, "NP", None), "values", ())
        for phase, amount in zip(phase_values, np_values):
            label = str(phase.item() if hasattr(phase, "item") else phase)
            try:
                phase_fractions[label] = float(amount)
            except (TypeError, ValueError):
                continue
        return CalphadResult("pycalphad", self.version, manifest.database_id, request.temperature_k, request.pressure_pa, phase_fractions, {"components": components, "phases": phases, "equilibrium": str(result)}, database_sha256=manifest.sha256, database_manifest=manifest.to_dict())
