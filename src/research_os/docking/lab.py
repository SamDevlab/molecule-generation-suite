from __future__ import annotations
from pathlib import Path
from typing import Any
import uuid
from research_os.core.hashing import sha256_file
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.docking.rules import docking_rules
from research_os.docking.schema import DockingRequest, GridBox
from research_os.engines.vina import VinaEngine
from research_os.labs.base import Lab
from research_os.proof.engine import ProofEngine

class DockingLab(Lab):
    name = "DockingLab"
    def __init__(self, engine=None): self.engine = engine or VinaEngine()
    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        grid = raw.get("grid") or {}
        return {"receptor_path": str(raw.get("receptor_path")) if raw.get("receptor_path") is not None else None, "ligand_path": str(raw.get("ligand_path")) if raw.get("ligand_path") is not None else None, "grid": {"center_x": float(grid.get("center_x", 0)), "center_y": float(grid.get("center_y", 0)), "center_z": float(grid.get("center_z", 0)), "size_x": float(grid.get("size_x", 0)), "size_y": float(grid.get("size_y", 0)), "size_z": float(grid.get("size_z", 0))}, "exhaustiveness": int(raw.get("exhaustiveness", 8)), "cpu": int(raw.get("cpu", 1)), "seed": int(raw.get("seed", 42)), "output_path": str(raw.get("output_path")) if raw.get("output_path") is not None else None, "target_id": raw.get("target_id")}
    def rules(self): return docking_rules(self.engine)
    def run(self, raw: dict[str, Any], experiment: str = "vina_docking") -> RunManifest:
        n = self.normalize(raw); m = RunManifest(lab=self.name, experiment=experiment, inputs=n, config={"engine": type(self.engine).__name__, "engine_version": self.engine.version}); ProofEngine().evaluate(m, self.rules())
        if not m.passed: return m
        m.evidence.append(Evidence(evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", kind="docking_input_artifacts", level=EvidenceLevel.E2_COMPUTATIONAL, source="DockingLab artifact integrity", payload={"receptor": {"path": n["receptor_path"], "sha256": sha256_file(n["receptor_path"])}, "ligand": {"path": n["ligand_path"], "sha256": sha256_file(n["ligand_path"])}, "grid": n["grid"], "seed": n["seed"], "exhaustiveness": n["exhaustiveness"]}))
        req = DockingRequest(receptor_path=n["receptor_path"], ligand_path=n["ligand_path"], grid=GridBox(**n["grid"]), exhaustiveness=n["exhaustiveness"], cpu=n["cpu"], seed=n["seed"], output_path=n["output_path"])
        try: result = self.engine.run(req)
        except Exception as exc:
            m.gates.append(GateResult("GATE-DOCKING", "DOCK-RUN-001", GateStatus.FAIL, "docking engine execution raised an exception", diagnostics={"error_type": type(exc).__name__, "error": str(exc)})); return m
        if result.returncode != 0:
            m.gates.append(GateResult("GATE-DOCKING", "DOCK-RUN-001", GateStatus.FAIL, "docking engine returned non-zero status", diagnostics={"returncode": result.returncode, "stderr": result.stderr[-2000:]})); return m
        payload = result.to_dict()
        if result.output_path and Path(result.output_path).is_file(): payload["output_sha256"] = sha256_file(result.output_path)
        ev = Evidence(evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", kind="molecular_docking_result", level=EvidenceLevel.E2_COMPUTATIONAL, source=f"{result.engine} {result.engine_version or 'unknown'}", payload=payload); m.evidence.append(ev)
        m.gates.append(GateResult("GATE-DOCKING", "DOCK-RUN-001", GateStatus.PASS, "docking engine completed successfully", evidence_ids=(ev.evidence_id,), diagnostics={"best_affinity_kcal_mol": result.best_affinity_kcal_mol})); return m
