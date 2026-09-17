from __future__ import annotations

from research_os.core.types import GateResult, GateStatus
from research_os.proof.rules import Rule, require_fields


def propulsion_rules() -> list[Rule]:
    rules = [require_fields("PROP-INPUT-001", ("combustion", "exit_pressure_pa"))]

    def conditions(ctx, evidence):
        pe = float(ctx["exit_pressure_pa"])
        eta = float(ctx.get("nozzle_efficiency", 1.0))
        if pe < 0:
            return GateResult("GATE-PROP-CONDITIONS", "PROP-COND-001", GateStatus.FAIL, "exit pressure cannot be negative")
        if not (0 < eta <= 1.0):
            return GateResult("GATE-PROP-CONDITIONS", "PROP-COND-001", GateStatus.FAIL, "nozzle efficiency must be in (0,1]")
        return GateResult("GATE-PROP-CONDITIONS", "PROP-COND-001", GateStatus.PASS, "propulsion request conditions structurally valid")

    rules.append(Rule("PROP-COND-001", "Validate exit pressure and nozzle efficiency", conditions))
    return rules
