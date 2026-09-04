from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class FractionBasis(str, Enum):
    MOLE = "mole"
    MASS = "mass"


@dataclass(frozen=True)
class FuelComponent:
    name: str | None = None
    smiles: str | None = None
    fraction: float = 1.0
    source_id: str | None = None

    def identity(self) -> str | None:
        return self.name or self.smiles


@dataclass(frozen=True)
class FuelConditions:
    temperature_k: float | None = None
    pressure_pa: float | None = None
    phase: str | None = None


@dataclass(frozen=True)
class FuelRecord:
    components: tuple[FuelComponent, ...]
    fraction_basis: FractionBasis = FractionBasis.MOLE
    conditions: FuelConditions = field(default_factory=FuelConditions)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
