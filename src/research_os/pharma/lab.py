from __future__ import annotations
from typing import Any
import uuid
from research_os.core.provenance import provenance_from_mapping
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.docking.lab import DockingLab
from research_os.knowledge.claims import claim_from_run
from research_os.labs.base import Lab
from research_os.molecule.lab import MoleculeLab
from research_os.pharma.rules import pharma_rules
from research_os.proof.engine import ProofEngine

class PharmaLab(Lab):
    """Molecular characterization plus optional docking; never equates docking with clinical efficacy."""
    name = "PharmaLab"
    def __init__(self, molecule_lab=None, docking_lab=None): self.molecule_lab = molecule_lab or MoleculeLab(); self.docking_lab = docking_lab or DockingLab()
    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        smiles = raw.get("smiles") or raw.get("SMILES"); return {"smiles": smiles.strip() if isinstance(smiles, str) else smiles, "name": raw.get("name"), "molecule_id": raw.get("molecule_id") or raw.get("id"), "docking": dict(raw.get("docking")) if raw.get("docking") else None, "provenance": dict(raw.get("provenance") or {})}
    def rules(self): return pharma_rules()
    def run(self, raw: dict[str, Any], experiment: str = "pharma_screening") -> RunManifest:
        n = self.normalize(raw); m = RunManifest(lab=self.name, experiment=experiment, inputs=n); prv = provenance_from_mapping(n.get("provenance"), default_source_id="pharma-input"); m.provenance.append(prv); ProofEngine().evaluate(m, self.rules())
        if not m.passed: return m
        mr = self.molecule_lab.run({"smiles": n["smiles"], "name": n.get("name"), "id": n.get("molecule_id"), "source": prv.source_id}, experiment="pharma_molecular_characterization")
        if not mr.passed:
            loss = mr.first_loss; m.gates.append(GateResult("GATE-PHARMA-MOLECULE", "PHARMA-MOL-002", loss.status if loss else GateStatus.FAIL, "nested MoleculeLab validation failed", diagnostics={"nested_run_id": mr.run_id, "nested_first_loss": loss.rule_id if loss else None})); return m
        mev = Evidence(evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", kind="pharma_molecular_characterization", level=EvidenceLevel.E2_COMPUTATIONAL, source="MoleculeLab/RDKit", provenance_ids=(prv.provenance_id,), payload={"nested_run_id": mr.run_id, "nested_evidence": [e.payload for e in mr.evidence]}); m.evidence.append(mev); m.gates.append(GateResult("GATE-PHARMA-MOLECULE", "PHARMA-MOL-002", GateStatus.PASS, "molecular characterization completed", evidence_ids=(mev.evidence_id,), diagnostics={"nested_run_id": mr.run_id}))
        if n.get("docking"):
            dr = self.docking_lab.run(dict(n["docking"]), experiment="pharma_target_docking")
            if not dr.passed:
                loss = dr.first_loss; m.gates.append(GateResult("GATE-PHARMA-DOCKING", "PHARMA-DOCK-001", loss.status if loss else GateStatus.FAIL, "requested docking did not complete successfully", diagnostics={"nested_run_id": dr.run_id, "nested_first_loss": loss.rule_id if loss else None})); return m
            result = next((e for e in reversed(dr.evidence) if e.kind == "molecular_docking_result"), None)
            dev = Evidence(evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", kind="pharma_docking_result", level=EvidenceLevel.E2_COMPUTATIONAL, source="DockingLab", provenance_ids=(prv.provenance_id,), payload={"nested_run_id": dr.run_id, "result": result.payload if result else {}, "interpretation_limit": "docking score is computational evidence, not clinical efficacy or measured binding affinity"}); m.evidence.append(dev); m.gates.append(GateResult("GATE-PHARMA-DOCKING", "PHARMA-DOCK-001", GateStatus.PASS, "requested docking completed", evidence_ids=(dev.evidence_id,), diagnostics={"nested_run_id": dr.run_id}))
        return m
    def molecular_claim(self, run):
        return claim_from_run(run, "Molecular structure was computationally characterized under the recorded protocol.", minimum_evidence_level=EvidenceLevel.E2_COMPUTATIONAL, limitations=("This claim does not establish efficacy, safety, ADMET, or clinical benefit.",))
