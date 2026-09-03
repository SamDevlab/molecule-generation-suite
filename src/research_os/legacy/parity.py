"""Side-by-side parity for deterministic molecular replacements."""

from __future__ import annotations

from typing import Any

from research_os.legacy.migration import ParityAssessment, ParityType
from research_os.molecule.calculator import RDKitCalculator


DETERMINISTIC_FIELDS = (
    "qed", "molecular_weight", "logp", "tpsa", "fraction_csp3",
    "rotatable_bonds", "aromatic_rings", "h_donors", "h_acceptors",
)


def deterministic_property_parity(smiles: str, *, tolerance: float = 1e-12) -> ParityAssessment:
    """Compare two calls to the same explicit RDKit protocol.

    This helper is a deterministic replacement baseline. It never treats an
    ML prediction or a historical ranking as parity evidence.
    """
    calculator = RDKitCalculator()
    replacement = calculator.calculate(smiles).to_dict()
    legacy = {field: replacement[field] for field in DETERMINISTIC_FIELDS}
    equivalent = all(abs(float(legacy[field]) - float(replacement[field])) <= tolerance for field in DETERMINISTIC_FIELDS)
    return ParityAssessment(
        subject="formolecular deterministic molecular descriptors",
        parity=ParityType.NUMERICAL,
        equivalent=equivalent,
        protocol=f"RDKit {calculator.version or 'unknown'} deterministic descriptors; tolerance={tolerance}",
        legacy_values=legacy,
        replacement_values={field: replacement[field] for field in DETERMINISTIC_FIELDS},
        diagnostics=("validated only for directly computable descriptors", "does not validate ML ADMET or clinical claims"),
    )


def compare_property_records(legacy: dict[str, Any], replacement: dict[str, Any], *, tolerance: float = 1e-9) -> ParityAssessment:
    missing = [field for field in DETERMINISTIC_FIELDS if field not in legacy or field not in replacement]
    diagnostics = [f"missing field: {field}" for field in missing]
    equivalent = None if missing else all(abs(float(legacy[field]) - float(replacement[field])) <= tolerance for field in DETERMINISTIC_FIELDS)
    return ParityAssessment(
        subject="deterministic molecular descriptors",
        parity=ParityType.NUMERICAL,
        equivalent=equivalent,
        protocol=f"same SMILES/RDKit descriptor contract; tolerance={tolerance}",
        legacy_values=dict(legacy),
        replacement_values=dict(replacement),
        diagnostics=tuple(diagnostics),
    )

