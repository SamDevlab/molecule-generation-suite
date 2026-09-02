from __future__ import annotations

from research_os.engines.combustion import EquilibriumRequest, EquilibriumResult

try:
    import cantera as ct
except ImportError as exc:
    ct = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class CanteraUnavailableError(RuntimeError):
    pass


class CanteraEquilibriumEngine:
    """Adiabatic constant-pressure equilibrium adapter; not experimental validation."""

    @property
    def available(self) -> bool:
        return ct is not None

    @property
    def version(self) -> str | None:
        return getattr(ct, "__version__", None) if ct is not None else None

    def simulate_equilibrium(self, request: EquilibriumRequest) -> EquilibriumResult:
        if ct is None:
            raise CanteraUnavailableError("Cantera is not installed") from _IMPORT_ERROR
        gas = ct.Solution(request.mechanism)
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
        )
