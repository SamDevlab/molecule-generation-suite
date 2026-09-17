from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_os.core.hashing import sha256_file, sha256_json
from research_os.engines.combustion import EquilibriumRequest, EquilibriumResult
from research_os.engines.manifest import EngineAvailability, EngineKind, EngineManifest, EngineReadiness, EngineStatus

try:
    import cantera as ct
except ImportError as exc:
    ct = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class CanteraUnavailableError(RuntimeError):
    pass


class CanteraMechanismUnavailableError(RuntimeError):
    """The requested mechanism/phase cannot be resolved; no result is valid."""


@dataclass(frozen=True)
class MechanismManifest:
    mechanism_id: str
    name: str
    source: str
    sha256: str | None
    phase_name: str | None
    species_count: int | None
    reaction_count: int | None
    engine_version: str | None
    license: str | None = None
    metadata: dict[str, Any] | None = None
    manifest_hash: str | None = None

    def __post_init__(self) -> None:
        if self.manifest_hash is None:
            object.__setattr__(self, "manifest_hash", sha256_json({key: getattr(self, key) for key in ("mechanism_id", "name", "source", "sha256", "phase_name", "species_count", "reaction_count", "engine_version", "license", "metadata")}))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def mechanism_hash(self) -> str | None:
        return self.sha256


class CanteraEquilibriumEngine:
    """Adiabatic constant-pressure equilibrium adapter; not experimental validation."""

    @property
    def available(self) -> bool:
        return ct is not None

    @property
    def version(self) -> str | None:
        return getattr(ct, "__version__", None) if ct is not None else None

    def _resolve(self, mechanism: str) -> Path | str:
        if ct is None:
            raise CanteraUnavailableError("Cantera is not installed") from _IMPORT_ERROR
        candidate = Path(mechanism)
        if candidate.is_file():
            return candidate
        for directory in getattr(ct, "get_data_directories", lambda: ())():
            found = Path(directory) / mechanism
            if found.is_file():
                return found
        raise CanteraMechanismUnavailableError(f"Cantera mechanism is unavailable: {mechanism}")

    def mechanism_manifest(self, request: EquilibriumRequest, *, environment_id: str | None = None) -> MechanismManifest:
        source = self._resolve(request.mechanism)
        path = Path(source)
        try:
            gas = ct.Solution(str(source), request.phase) if request.phase else ct.Solution(str(source))
        except (OSError, RuntimeError, ValueError) as exc:
            raise CanteraMechanismUnavailableError(f"Cantera mechanism phase could not be loaded: {request.mechanism}") from exc
        return MechanismManifest(request.mechanism, request.mechanism, str(path), sha256_file(path), getattr(gas, "name", request.phase), int(gas.n_species), int(gas.n_reactions), self.version)

    def engine_manifest(self, request: EquilibriumRequest, *, input_hashes: tuple[str, ...] = (), output_hashes: tuple[str, ...] = (), environment_id: str | None = None, executed: bool = False, mechanism: MechanismManifest | None = None) -> EngineManifest:
        mech = mechanism or self.mechanism_manifest(request, environment_id=environment_id)
        return EngineManifest("cantera", "Cantera", EngineKind.PHYSICS_ENGINE, self.version, EngineAvailability.AVAILABLE, EngineStatus.SUPPORTED_AND_EXECUTED if executed else EngineStatus.AVAILABLE_BUT_NOT_EXECUTED, EngineReadiness.REFERENCE_VALIDATED if executed else EngineReadiness.PROTOCOL_READY, library_version=self.version, configuration={"mechanism": request.mechanism, "phase": request.phase, "protocol_id": request.protocol_id}, protocol_id=request.protocol_id, input_hashes=input_hashes, output_hashes=output_hashes, environment_id=environment_id, limitations=("equilibrium simulation is not experiment",), metadata={"mechanism_manifest_hash": mech.manifest_hash, "mechanism_sha256": mech.sha256, "mechanism_hash": mech.sha256})

    def simulate_equilibrium(self, request: EquilibriumRequest) -> EquilibriumResult:
        if ct is None:
            raise CanteraUnavailableError("Cantera is not installed") from _IMPORT_ERROR
        mechanism = self.mechanism_manifest(request)
        gas = ct.Solution(mechanism.source, request.phase) if request.phase else ct.Solution(mechanism.source)
        gas.TP = request.temperature_k, request.pressure_pa
        gas.set_equivalence_ratio(request.equivalence_ratio, fuel=request.fuel, oxidizer=request.oxidizer, basis=request.basis)
        gas.equilibrate("HP")
        major = {name: float(x) for name, x in zip(gas.species_names, gas.X) if float(x) >= 1e-4}
        major = dict(sorted(major.items(), key=lambda item: item[1], reverse=True)[:20])
        return EquilibriumResult(
            adiabatic_temperature_k=float(gas.T), pressure_pa=float(gas.P),
            mean_molecular_weight=float(gas.mean_molecular_weight), major_species_mole_fractions=major,
            engine="Cantera", engine_version=self.version, mechanism=request.mechanism,
            gamma=float(gas.cp_mass / gas.cv_mass), cp_mass_j_kg_k=float(gas.cp_mass), cv_mass_j_kg_k=float(gas.cv_mass),
            mechanism_id=mechanism.mechanism_id, mechanism_sha256=mechanism.sha256, phase_name=mechanism.phase_name,
            species_count=mechanism.species_count, reaction_count=mechanism.reaction_count,
            mechanism_manifest=mechanism.to_dict(),
            engine_manifest=self.engine_manifest(request, executed=True, mechanism=mechanism).to_dict(),
            solver_assumptions=("adiabatic", "constant pressure", "chemical equilibrium HP", "ideal-gas phase model as defined by the mechanism"),
        )
