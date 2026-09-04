from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable


class UnitError(ValueError):
    pass


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str
    dimension: str
    si_value: float
    si_unit: str

    def to_dict(self) -> dict[str, float | str]:
        return asdict(self)


def _identity(v: float) -> float:
    return v


def _c_to_k(v: float) -> float:
    return v + 273.15


def _kcalmol_to_jmol(v: float) -> float:
    return v * 4184.0


_UNITS: dict[str, tuple[str, str, str, Callable[[float], float]]] = {
    "k": ("temperature", "K", "K", _identity), "kelvin": ("temperature", "K", "K", _identity),
    "c": ("temperature", "degC", "K", _c_to_k), "°c": ("temperature", "degC", "K", _c_to_k), "degc": ("temperature", "degC", "K", _c_to_k),
    "pa": ("pressure", "Pa", "Pa", _identity), "kpa": ("pressure", "kPa", "Pa", lambda v: v * 1_000.0),
    "mpa": ("pressure", "MPa", "Pa", lambda v: v * 1_000_000.0), "bar": ("pressure", "bar", "Pa", lambda v: v * 100_000.0), "atm": ("pressure", "atm", "Pa", lambda v: v * 101_325.0),
    "m": ("length", "m", "m", _identity), "mm": ("length", "mm", "m", lambda v: v * 1e-3), "um": ("length", "um", "m", lambda v: v * 1e-6), "µm": ("length", "um", "m", lambda v: v * 1e-6), "nm": ("length", "nm", "m", lambda v: v * 1e-9),
    "j/mol": ("molar_energy", "J/mol", "J/mol", _identity), "kj/mol": ("molar_energy", "kJ/mol", "J/mol", lambda v: v * 1_000.0), "kcal/mol": ("molar_energy", "kcal/mol", "J/mol", _kcalmol_to_jmol), "kcal mol-1": ("molar_energy", "kcal/mol", "J/mol", _kcalmol_to_jmol),
    "g/mol": ("molar_mass", "g/mol", "kg/mol", lambda v: v * 1e-3), "kg/mol": ("molar_mass", "kg/mol", "kg/mol", _identity),
    "%": ("fraction_percent", "%", "1", lambda v: v / 100.0), "1": ("dimensionless", "1", "1", _identity),
}


def quantity(value: float, unit: str, *, dimension: str | None = None) -> Quantity:
    key = unit.strip().lower()
    if key not in _UNITS:
        raise UnitError(f"unsupported unit: {unit}")
    actual_dimension, display_unit, si_unit, converter = _UNITS[key]
    if dimension is not None and actual_dimension != dimension:
        raise UnitError(f"unit {unit} has dimension {actual_dimension}, expected {dimension}")
    numeric = float(value)
    return Quantity(numeric, display_unit, actual_dimension, converter(numeric), si_unit)


def si_value(value: float, unit: str, *, dimension: str | None = None) -> float:
    return quantity(value, unit, dimension=dimension).si_value
