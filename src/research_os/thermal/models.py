from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PlanarConductionRequest:
    hot_temperature_k: float
    cold_temperature_k: float
    conductivity_w_mk: float
    thickness_m: float
    area_m2: float = 1.0


@dataclass(frozen=True)
class PlanarConductionResult:
    delta_temperature_k: float
    thermal_resistance_k_w: float
    heat_rate_w: float
    heat_flux_w_m2: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def planar_conduction(req: PlanarConductionRequest) -> PlanarConductionResult:
    if req.hot_temperature_k <= 0 or req.cold_temperature_k <= 0:
        raise ValueError("absolute temperatures must be > 0 K")
    if req.conductivity_w_mk <= 0:
        raise ValueError("thermal conductivity must be > 0 W/(m K)")
    if req.thickness_m <= 0 or req.area_m2 <= 0:
        raise ValueError("thickness and area must be > 0")
    if req.hot_temperature_k < req.cold_temperature_k:
        raise ValueError("hot temperature must be >= cold temperature")

    dt = req.hot_temperature_k - req.cold_temperature_k
    resistance = req.thickness_m / (req.conductivity_w_mk * req.area_m2)
    heat_rate = dt / resistance if dt else 0.0
    return PlanarConductionResult(
        delta_temperature_k=dt,
        thermal_resistance_k_w=resistance,
        heat_rate_w=heat_rate,
        heat_flux_w_m2=heat_rate / req.area_m2,
    )
