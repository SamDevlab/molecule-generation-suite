from __future__ import annotations

from typing import Any
import uuid

from research_os.core.types import Evidence, EvidenceLevel, RunManifest
from research_os.fuel.rules import fuel_components_rule, fuel_conditions_rule, fuel_fraction_rule
from research_os.labs.base import Lab
from research_os.molecule.lab import MoleculeLab
from research_os.proof.engine import ProofEngine
from research_os.proof.rules import Rule


class FuelLab(Lab):
    """Fuel identity/composition lab; combustion and Isp are explicitly out of scope."""

    name = "FuelLab"

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        components = raw.get("components")
        if components is None and (raw.get("smiles") or raw.get("SMILES") or raw.get("name")):
            components = [{"name": raw.get("name"), "smiles": raw.get("smiles") or raw.get("SMILES"), "fraction": 1.0}]
        normalized_components = []
        for comp in components or []:
            normalized_components.append({"name": comp.get("name"), "smiles": comp.get("smiles") or comp.get("SMILES"), "fraction": float(comp.get("fraction", 1.0)), "source_id": comp.get("source_id")})
        conditions = raw.get("conditions") or {}
        return {"components": normalized_components, "fraction_basis": raw.get("fraction_basis", "mole"), "conditions": {"temperature_k": conditions.get("temperature_k"), "pressure_pa": conditions.get("pressure_pa"), "phase": conditions.get("phase")}, "provenance": raw.get("provenance") or {}}

    def rules(self) -> list[Rule]:
        return [fuel_components_rule(), fuel_fraction_rule(), fuel_conditions_rule()]

    def run(self, raw: dict[str, Any], experiment: str = "fuel_catalog") -> RunManifest:
        normalized = self.normalize(raw)
        manifest = RunManifest(lab=self.name, experiment=experiment, inputs=normalized)
        ProofEngine().evaluate(manifest, self.rules())
        if not manifest.passed:
            return manifest
        manifest.evidence.append(Evidence(evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", kind="fuel_composition", level=EvidenceLevel.E2_COMPUTATIONAL, source="FuelLab composition normalizer v0", payload={"fraction_basis": normalized["fraction_basis"], "components": normalized["components"], "conditions": normalized["conditions"]}))
        molecular_components = []
        for index, component in enumerate(normalized["components"]):
            if not component.get("smiles"):
                continue
            component_run = MoleculeLab().run({"smiles": component["smiles"], "name": component.get("name")}, experiment="fuel_component_molecular_properties")
            molecular_components.append({"component_index": index, "run_id": component_run.run_id, "passed": component_run.passed, "first_loss": component_run.first_loss.rule_id if component_run.first_loss else None, "evidence": [e.payload for e in component_run.evidence]})
        if molecular_components:
            manifest.evidence.append(Evidence(evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", kind="fuel_component_molecular_properties", level=EvidenceLevel.E2_COMPUTATIONAL, source="MoleculeLab/RDKit delegation", payload={"components": molecular_components}))
        return manifest
