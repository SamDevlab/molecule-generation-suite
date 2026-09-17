from __future__ import annotations

from math import isfinite
from research_os.core.types import GateResult, GateStatus
from research_os.proof.rules import Rule


def fuel_components_rule(rule_id: str = "FUEL-COMP-001") -> Rule:
    def evaluate(ctx, evidence):
        components = ctx.get("components") or []
        if not components:
            return GateResult("GATE-COMPOSITION", rule_id, GateStatus.FAIL, "fuel has no components")
        missing_identity = [i for i, c in enumerate(components) if not (c.get("name") or c.get("smiles"))]
        if missing_identity:
            return GateResult("GATE-COMPOSITION", rule_id, GateStatus.FAIL, "one or more fuel components have no identity", diagnostics={"component_indices": missing_identity})
        return GateResult("GATE-COMPOSITION", rule_id, GateStatus.PASS, "fuel components identified")
    return Rule(rule_id, "Require at least one identified fuel component", evaluate)


def fuel_fraction_rule(rule_id: str = "FUEL-COMP-002", tolerance: float = 1e-6) -> Rule:
    def evaluate(ctx, evidence):
        values = [c.get("fraction") for c in (ctx.get("components") or [])]
        if any(v is None or not isfinite(float(v)) or float(v) <= 0 for v in values):
            return GateResult("GATE-COMPOSITION", rule_id, GateStatus.FAIL, "component fractions must be finite and positive", diagnostics={"fractions": values})
        total = sum(float(v) for v in values)
        if abs(total - 1.0) > tolerance:
            return GateResult("GATE-COMPOSITION", rule_id, GateStatus.FAIL, "component fractions do not sum to one", diagnostics={"sum": total, "tolerance": tolerance})
        return GateResult("GATE-COMPOSITION", rule_id, GateStatus.PASS, "component fractions normalized", diagnostics={"sum": total})
    return Rule(rule_id, "Require normalized fuel composition fractions", evaluate)


def fuel_conditions_rule(rule_id: str = "FUEL-COND-001") -> Rule:
    def evaluate(ctx, evidence):
        conditions = ctx.get("conditions") or {}
        t, p = conditions.get("temperature_k"), conditions.get("pressure_pa")
        invalid = {}
        if t is not None and float(t) <= 0: invalid["temperature_k"] = t
        if p is not None and float(p) <= 0: invalid["pressure_pa"] = p
        if invalid:
            return GateResult("GATE-CONDITIONS", rule_id, GateStatus.FAIL, "non-physical thermodynamic condition values", diagnostics=invalid)
        return GateResult("GATE-CONDITIONS", rule_id, GateStatus.PASS, "declared conditions are structurally valid")
    return Rule(rule_id, "Temperature/pressure, when provided, must be positive absolute values", evaluate)
