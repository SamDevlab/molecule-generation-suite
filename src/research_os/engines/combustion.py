from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class EquilibriumRequest:
    fuel: str | Mapping[str, float]
    oxidizer: str | Mapping[str, float]
    equivalence_ratio: float = 1.0
    temperature_k: float = 298.15
    pressure_pa: float = 101325.0
    basis: str = "mole"
    mechanism: str = "gri30.yaml"
    phase: str | None = None
    protocol_id: str = "cantera.equilibrium.hp.v1"


@dataclass(frozen=True)
class EquilibriumResult:
    adiabatic_temperature_k: float
    pressure_pa: float
    mean_molecular_weight: float
    major_species_mole_fractions: dict[str, float]
    engine: str
    engine_version: str | None
    mechanism: str
    gamma: float | None = None
    cp_mass_j_kg_k: float | None = None
    cv_mass_j_kg_k: float | None = None
    model: str = "adiabatic_chemical_equilibrium_HP"
    mechanism_id: str | None = None
    mechanism_sha256: str | None = None
    phase_name: str | None = None
    species_count: int | None = None
    reaction_count: int | None = None
    mechanism_manifest: dict[str, Any] | None = None
    engine_manifest: dict[str, Any] | None = None
    solver_assumptions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CombustionEngine(Protocol):
    @property
    def available(self) -> bool: ...
    @property
    def version(self) -> str | None: ...
    def simulate_equilibrium(self, request: EquilibriumRequest) -> EquilibriumResult: ...
