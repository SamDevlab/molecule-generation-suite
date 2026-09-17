from __future__ import annotations
from research_os.proof.rules import Rule, require_fields
def pharma_rules() -> list[Rule]: return [require_fields("PHARMA-MOL-001", ("smiles",))]
