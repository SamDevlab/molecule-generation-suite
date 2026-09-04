from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from research_os.molecule.calculator import MolecularProperties, RDKitCalculator


LEGACY_DETERMINISTIC_COLUMNS = {
    "Peso_Molar": "molecular_weight", "LogP": "logp", "TPSA": "tpsa", "Score_QED": "qed",
    "ADMET_FractionCSP3": "fraction_csp3", "ADMET_RotatableBonds": "rotatable_bonds",
    "ADMET_AromaticRings": "aromatic_rings", "ADMET_HDonors": "h_donors", "ADMET_HAcceptors": "h_acceptors",
}


@dataclass(frozen=True)
class LegacyAuditItem:
    legacy_column: str
    deterministic_property: str
    stored_value: float
    recalculated_value: float
    absolute_difference: float


class LegacyFormolecularAdapter:
    """Migration bridge for rows from the current formolecular CSVs."""

    def __init__(self, calculator: RDKitCalculator | None = None):
        self.calculator = calculator or RDKitCalculator()

    def to_lab_input(self, row: dict[str, Any]) -> dict[str, Any]:
        return {"smiles": row.get("SMILES") or row.get("smiles"), "id": row.get("ID") or row.get("id"), "name": row.get("Nome") or row.get("name"), "source": row.get("source") or "legacy_formolecular"}

    def audit_deterministic_columns(self, row: dict[str, Any]) -> list[LegacyAuditItem]:
        smiles = row.get("SMILES") or row.get("smiles")
        props: MolecularProperties = self.calculator.calculate(smiles)
        calculated = props.to_dict()
        findings: list[LegacyAuditItem] = []
        for legacy_column, prop_name in LEGACY_DETERMINISTIC_COLUMNS.items():
            value = row.get(legacy_column)
            if value is None:
                continue
            try:
                stored = float(value)
            except (TypeError, ValueError):
                continue
            current = float(calculated[prop_name])
            findings.append(LegacyAuditItem(legacy_column=legacy_column, deterministic_property=prop_name, stored_value=stored, recalculated_value=current, absolute_difference=abs(stored - current)))
        return findings
