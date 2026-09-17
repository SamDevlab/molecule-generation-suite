from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any
from research_os.core.types import GateResult, GateStatus, Evidence

RuleFn = Callable[[dict[str, Any], list[Evidence]], GateResult]

@dataclass(frozen=True)
class Rule:
    rule_id: str
    description: str
    evaluator: RuleFn


def require_fields(rule_id: str, fields: tuple[str, ...]) -> Rule:
    def evaluate(ctx, evidence):
        missing = [f for f in fields if ctx.get(f) is None]
        if missing:
            return GateResult(
                gate_id="GATE-INPUT", rule_id=rule_id, status=GateStatus.FAIL,
                reason="required fields missing", diagnostics={"missing": missing},
            )
        return GateResult("GATE-INPUT", rule_id, GateStatus.PASS, "required fields present")
    return Rule(rule_id, f"Require fields: {', '.join(fields)}", evaluate)


def require_evidence_level(rule_id: str, minimum_levels: set[str]) -> Rule:
    def evaluate(ctx, evidence):
        levels = {e.level.value for e in evidence}
        if levels.intersection(minimum_levels):
            ids = tuple(e.evidence_id for e in evidence if e.level.value in minimum_levels)
            return GateResult("GATE-EVIDENCE", rule_id, GateStatus.PASS, "evidence threshold met", ids)
        return GateResult(
            "GATE-EVIDENCE", rule_id, GateStatus.INSUFFICIENT_EVIDENCE,
            "no evidence at required level", diagnostics={"observed_levels": sorted(levels)}
        )
    return Rule(rule_id, "Require minimum evidence class", evaluate)
