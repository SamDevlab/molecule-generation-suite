from __future__ import annotations

from research_os.core.types import GateResult, GateStatus
from research_os.proof.rules import Rule, require_fields


def combustion_request_rules() -> list[Rule]:
    rules = [require_fields("COMB-INPUT-001", ("fuel", "oxidizer", "equivalence_ratio", "temperature_k", "pressure_pa"))]

    def numeric(ctx, evidence):
        phi = float(ctx["equivalence_ratio"])
        temp = float(ctx["temperature_k"])
        pressure = float(ctx["pressure_pa"])
        invalid = {}
        if phi <= 0: invalid["equivalence_ratio"] = phi
        if temp <= 0: invalid["temperature_k"] = temp
        if pressure <= 0: invalid["pressure_pa"] = pressure
        if invalid:
            return GateResult("GATE-CONDITIONS", "COMB-COND-001", GateStatus.FAIL, "invalid absolute combustion conditions", diagnostics=invalid)
        return GateResult("GATE-CONDITIONS", "COMB-COND-001", GateStatus.PASS, "combustion request conditions structurally valid")

    rules.append(Rule("COMB-COND-001", "Require positive equivalence ratio, temperature and pressure", numeric))
    return rules


def engine_available_rule(engine) -> Rule:
    def evaluate(ctx, evidence):
        if not engine.available:
            return GateResult("GATE-PHYSICS-ENGINE", "COMB-ENGINE-001", GateStatus.INDETERMINATE, "physics engine unavailable; no combustion result may be claimed", diagnostics={"engine": type(engine).__name__})
        return GateResult("GATE-PHYSICS-ENGINE", "COMB-ENGINE-001", GateStatus.PASS, "declared combustion physics engine is available", diagnostics={"engine": type(engine).__name__, "version": engine.version})
    return Rule("COMB-ENGINE-001", "Require an available physics engine", evaluate)
