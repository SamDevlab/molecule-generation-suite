from __future__ import annotations

from typing import Any
import uuid

from research_os.core.types import Evidence, EvidenceLevel, RunManifest
from research_os.labs.base import Lab
from research_os.molecule.calculator import RDKitCalculator, InvalidSmilesError, RDKitUnavailableError
from research_os.molecule.rules import rdkit_structure_rule
from research_os.proof.engine import ProofEngine
from research_os.proof.rules import Rule, require_fields


class MoleculeLab(Lab):
    """Scientific adapter around the existing formolecular domain."""

    name = "MoleculeLab"

    def __init__(self, calculator: RDKitCalculator | None = None):
        self.calculator = calculator or RDKitCalculator()

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        smiles = raw.get("smiles") or raw.get("SMILES")
        normalized = {"smiles": smiles.strip() if isinstance(smiles, str) else smiles}
        for key in ("id", "name", "source"):
            if raw.get(key) is not None:
                normalized[key] = raw[key]
        return normalized

    def rules(self) -> list[Rule]:
        return [require_fields("MOL-STRUCT-001", ("smiles",)), rdkit_structure_rule("MOL-STRUCT-002")]

    def run(self, raw: dict[str, Any], experiment: str = "deterministic_properties") -> RunManifest:
        normalized = self.normalize(raw)
        manifest = RunManifest(lab=self.name, experiment=experiment, inputs=normalized, config={"calculator": self.calculator.engine_name, "calculator_version": self.calculator.version})
        ProofEngine().evaluate(manifest, self.rules())
        if not manifest.passed:
            return manifest
        try:
            properties = self.calculator.calculate(normalized["smiles"])
        except (InvalidSmilesError, RDKitUnavailableError):
            return manifest
        evidence = Evidence(
            evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", kind="deterministic_molecular_properties",
            level=EvidenceLevel.E2_COMPUTATIONAL, source=f"RDKit {self.calculator.version or 'unknown'}",
            payload=properties.to_dict(),
        )
        manifest.evidence.append(evidence)
        return manifest
