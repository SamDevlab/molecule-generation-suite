from __future__ import annotations

from dataclasses import asdict, dataclass
import math

G0_M_S2 = 9.80665
R_UNIVERSAL_J_KMOL_K = 8314.46261815324

class PropulsionModelError(ValueError):
    pass

@dataclass(frozen=True)
class IdealNozzleRequest:
    chamber_temperature_k: float
    chamber_pressure_pa: float
    exit_pressure_pa: float
    gamma: float
    mean_molecular_weight_kg_kmol: float
    nozzle_efficiency: float = 1.0

@dataclass(frozen=True)
class IdealNozzleResult:
    ideal_exhaust_velocity_m_s: float
    effective_exhaust_velocity_m_s: float
    ideal_kinetic_specific_impulse_s: float
    gamma: float
    specific_gas_constant_j_kg_k: float
    chamber_temperature_k: float
    chamber_pressure_pa: float
    exit_pressure_pa: float
    nozzle_efficiency: float
    model: str = "ideal_isentropic_nozzle_kinetic_only"
    def to_dict(self): return asdict(self)

class IdealIsentropicNozzleEngine:
    available = True
    version = "1"

    def calculate(self, request: IdealNozzleRequest) -> IdealNozzleResult:
        t, pc, pe = float(request.chamber_temperature_k), float(request.chamber_pressure_pa), float(request.exit_pressure_pa)
        gamma, mw, eta = float(request.gamma), float(request.mean_molecular_weight_kg_kmol), float(request.nozzle_efficiency)
        if t <= 0 or pc <= 0 or pe < 0 or pe >= pc:
            raise PropulsionModelError("require T>0, Pc>0, and 0<=Pe<Pc")
        if gamma <= 1.0: raise PropulsionModelError("gamma must be > 1")
        if mw <= 0: raise PropulsionModelError("mean molecular weight must be > 0")
        if not (0 < eta <= 1.0): raise PropulsionModelError("nozzle efficiency must be in (0, 1]")
        r_specific = R_UNIVERSAL_J_KMOL_K / mw
        pressure_term = 1.0 - (pe / pc) ** ((gamma - 1.0) / gamma)
        ideal_v = math.sqrt((2.0 * gamma / (gamma - 1.0)) * r_specific * t * pressure_term)
        effective_v = ideal_v * math.sqrt(eta)
        return IdealNozzleResult(ideal_exhaust_velocity_m_s=ideal_v, effective_exhaust_velocity_m_s=effective_v, ideal_kinetic_specific_impulse_s=effective_v / G0_M_S2, gamma=gamma, specific_gas_constant_j_kg_k=r_specific, chamber_temperature_k=t, chamber_pressure_pa=pc, exit_pressure_pa=pe, nozzle_efficiency=eta)
