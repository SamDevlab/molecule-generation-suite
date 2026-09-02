from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any, Protocol

@dataclass(frozen=True)
class CalphadRequest:
    composition: dict[str, float]
    fraction_basis: str
    temperature_k: float | None = None
    pressure_pa: float = 101325.0
    database: str | None = None
    phases: tuple[str, ...] = ()

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
    def to_dict(self) -> dict[str, Any]: return asdict(self)

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
