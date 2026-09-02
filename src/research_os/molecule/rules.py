from __future__ import annotations

from research_os.core.types import Evidence, GateResult, GateStatus
from research_os.proof.rules import Rule
from research_os.molecule.calculator import InvalidSmilesError, RDKitCalculator, RDKitUnavailableError


def rdkit_structure_rule(rule_id: str = "MOL-STRUCT-002") -> Rule:
    def evaluate(ctx: dict, evidence: list[Evidence]) -> GateResult:
        smiles = ctx.get("smiles")
        if not smiles:
            return GateResult("GATE-STRUCTURE", rule_id, GateStatus.FAIL, "SMILES missing")
        try:
            props = RDKitCalculator().calculate(smiles)
        except RDKitUnavailableError as exc:
            return GateResult("GATE-STRUCTURE", rule_id, GateStatus.INDETERMINATE, "RDKit unavailable", diagnostics={"error": str(exc)})
        except InvalidSmilesError as exc:
            return GateResult("GATE-STRUCTURE", rule_id, GateStatus.FAIL, "RDKit could not parse/sanitize molecular representation", diagnostics={"error": str(exc)})
        return GateResult("GATE-STRUCTURE", rule_id, GateStatus.PASS, "molecular representation parsed and sanitized by RDKit", diagnostics={"canonical_smiles": props.canonical_smiles})

    return Rule(rule_id, "Require a molecular representation that RDKit can parse and sanitize; this is not a physics/stability proof.", evaluate)
