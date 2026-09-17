from __future__ import annotations

from research_os.core.types import GateResult, GateStatus
from research_os.proof.rules import Rule, require_fields


def thermal_rules() -> list[Rule]:
    rules = [require_fields("THERM-INPUT-001", (
        "hot_temperature_k", "cold_temperature_k", "conductivity_w_mk", "thickness_m", "area_m2"
    ))]

    def validate(ctx, evidence):
        th = float(ctx["hot_temperature_k"])
        tc = float(ctx["cold_temperature_k"])
        k = float(ctx["conductivity_w_mk"])
        thickness = float(ctx["thickness_m"])
        area = float(ctx["area_m2"])
        diagnostics = {"hot_temperature_k": th, "cold_temperature_k": tc, "conductivity_w_mk": k, "thickness_m": thickness, "area_m2": area}
        if th <= 0 or tc <= 0:
            return GateResult("GATE-THERM-CONDITIONS", "THERM-COND-001", GateStatus.FAIL, "absolute temperatures must be > 0 K", diagnostics=diagnostics)
        if th < tc:
            return GateResult("GATE-THERM-CONDITIONS", "THERM-COND-001", GateStatus.FAIL, "hot temperature must be >= cold temperature", diagnostics=diagnostics)
        if k <= 0 or thickness <= 0 or area <= 0:
            return GateResult("GATE-THERM-CONDITIONS", "THERM-COND-001", GateStatus.FAIL, "conductivity, thickness and area must be > 0", diagnostics=diagnostics)
        return GateResult("GATE-THERM-CONDITIONS", "THERM-COND-001", GateStatus.PASS, "thermal boundary conditions structurally valid")

    rules.append(Rule("THERM-COND-001", "Validate planar steady-state conduction inputs", validate))
    return rules
