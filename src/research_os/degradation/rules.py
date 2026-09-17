from __future__ import annotations

from research_os.core.types import GateResult, GateStatus
from research_os.proof.rules import Rule, require_fields


def degradation_rules() -> list[Rule]:
    rules = [require_fields("DEG-INPUT-001", ("material", "environment", "temperature_k"))]

    def exposure(ctx, evidence):
        t = float(ctx["temperature_k"])
        if t <= 0:
            return GateResult("GATE-DEG-EXPOSURE", "DEG-EXPOSURE-001", GateStatus.FAIL, "temperature must be > 0 K")
        if not str(ctx["material"]).strip() or not str(ctx["environment"]).strip():
            return GateResult("GATE-DEG-EXPOSURE", "DEG-EXPOSURE-001", GateStatus.FAIL, "material and environment must be non-empty")
        return GateResult("GATE-DEG-EXPOSURE", "DEG-EXPOSURE-001", GateStatus.PASS, "degradation exposure record structurally valid")

    rules.append(Rule("DEG-EXPOSURE-001", "Validate degradation exposure context", exposure))
    return rules
