from __future__ import annotations
from pathlib import Path
from typing import Any
import uuid
from research_os.core.hashing import sha256_file
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.docking.rules import docking_rules
from research_os.docking.schema import DockingRequest, GridBox
from research_os.engines.vina import VinaEngine
from research_os.engines.manifest import EngineAvailability, EngineKind, EngineManifest, EngineReadiness, EngineStatus
from research_os.labs.base import Lab
from research_os.proof.engine import ProofEngine

class DockingLab(Lab):
    name = "DockingLab"
    def __init__(self, engine=None): self.engine = engine or VinaEngine()
    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        grid = raw.get("grid") or {}
        return {"receptor_path": str(raw.get("receptor_path")) if raw.get("receptor_path") is not None else None, "ligand_path": str(raw.get("ligand_path")) if raw.get("ligand_path") is not None else None, "grid": {"center_x": float(grid.get("center_x", 0)), "center_y": float(grid.get("center_y", 0)), "center_z": float(grid.get("center_z", 0)), "size_x": float(grid.get("size_x", 0)), "size_y": float(grid.get("size_y", 0)), "size_z": float(grid.get("size_z", 0))}, "exhaustiveness": int(raw.get("exhaustiveness", 8)), "cpu": int(raw.get("cpu", 1)), "seed": int(raw.get("seed", 42)), "output_path": str(raw.get("output_path")) if raw.get("output_path") is not None else None, "target_id": raw.get("target_id"), "species": raw.get("species"), "role": raw.get("role"), "require_species": bool(raw.get("require_species", False)), "require_preparation": bool(raw.get("require_preparation", False)), "receptor_metadata": dict(raw.get("receptor_metadata") or {}), "protocol_id": str(raw.get("protocol_id", "autodock-vina.docking.v1")), "timeout": float(raw.get("timeout", 300.0)), "prepared_ligand_manifest": raw.get("prepared_ligand_manifest"), "prepared_receptor_manifest": raw.get("prepared_receptor_manifest"), "num_modes": int(raw.get("num_modes", 9))}
    def rules(self): return docking_rules(self.engine)
    def run(self, raw: dict[str, Any], experiment: str = "vina_docking") -> RunManifest:
        n = self.normalize(raw); m = RunManifest(lab=self.name, experiment=experiment, inputs=n, config={"engine": type(self.engine).__name__, "engine_id": "autodock-vina", "engine_version": self.engine.version, "protocol_id": n["protocol_id"], "target_id": n.get("target_id"), "grid_hash": GridBox(**n["grid"]).grid_hash}); ProofEngine().evaluate(m, self.rules())
        if not m.passed: return m
        receptor_hash, ligand_hash = sha256_file(n["receptor_path"]), sha256_file(n["ligand_path"])
        m.evidence.append(Evidence(evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", kind="docking_input_artifacts", level=EvidenceLevel.E2_COMPUTATIONAL, source="DockingLab artifact integrity", payload={"receptor": {"path": n["receptor_path"], "sha256": receptor_hash}, "ligand": {"path": n["ligand_path"], "sha256": ligand_hash}, "grid": n["grid"], "grid_hash": GridBox(**n["grid"]).grid_hash, "seed": n["seed"], "exhaustiveness": n["exhaustiveness"], "num_modes": n["num_modes"], "target_id": n.get("target_id"), "species": n.get("species"), "prepared_ligand_manifest": n.get("prepared_ligand_manifest"), "prepared_receptor_manifest": n.get("prepared_receptor_manifest")}))
        req = DockingRequest(receptor_path=n["receptor_path"], ligand_path=n["ligand_path"], grid=GridBox(**n["grid"]), exhaustiveness=n["exhaustiveness"], cpu=n["cpu"], seed=n["seed"], output_path=n["output_path"], target_id=n.get("target_id"), species=n.get("species"), role=n.get("role"), receptor_metadata=n.get("receptor_metadata"), protocol_id=n["protocol_id"], timeout=n["timeout"], prepared_ligand_manifest=n.get("prepared_ligand_manifest"), prepared_receptor_manifest=n.get("prepared_receptor_manifest"), num_modes=n["num_modes"])
        try: result = self.engine.run(req)
        except (FileNotFoundError, ValueError) as exc:
            m.gates.append(GateResult("GATE-DOCKING", "DOCK-INPUT-002", GateStatus.FAIL, "docking input or grid validation failed", diagnostics={"error_type": type(exc).__name__, "error": str(exc)})); return m
        except Exception as exc:
            m.gates.append(GateResult("GATE-DOCKING", "DOCK-RUN-001", GateStatus.FAIL, "docking engine execution raised an exception", diagnostics={"error_type": type(exc).__name__, "error": str(exc)})); return m
        if result.returncode != 0:
            m.gates.append(GateResult("GATE-DOCKING", "DOCK-RUN-001", GateStatus.FAIL, "docking engine returned non-zero status", diagnostics={"returncode": result.returncode, "stderr": result.stderr[-2000:]})); return m
        payload = result.to_dict()
        if result.output_path and Path(result.output_path).is_file(): payload["output_sha256"] = sha256_file(result.output_path)
        engine_manifest = EngineManifest(
            "autodock-vina", "AutoDock Vina", EngineKind.COMPUTATIONAL_ENGINE, result.engine_version,
            EngineAvailability.AVAILABLE, EngineStatus.SUPPORTED_AND_EXECUTED if result.returncode == 0 else EngineStatus.EXECUTION_FAILED,
            EngineReadiness.REFERENCE_VALIDATED if result.returncode == 0 else EngineReadiness.PROTOCOL_READY,
            library_version=result.engine_version, configuration={"grid": n["grid"], "target_id": n.get("target_id"), "seed": n["seed"], "exhaustiveness": n["exhaustiveness"], "cpu": n["cpu"], "num_modes": n["num_modes"]},
            protocol_id=n["protocol_id"], input_hashes=(receptor_hash, ligand_hash), output_hashes=((payload.get("output_sha256"),) if payload.get("output_sha256") else ()),
            limitations=("docking score is computational evidence, not measured binding affinity",), metadata={"receptor_sha256": receptor_hash, "ligand_sha256": ligand_hash, "grid_hash": GridBox(**n["grid"]).grid_hash, "target_id": n.get("target_id"), "species": n.get("species")},
        )
        payload["engine_manifest"] = engine_manifest.to_dict()
        m.config["engine_manifest"] = engine_manifest.to_dict()
        ev = Evidence(evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", kind="molecular_docking_result", level=EvidenceLevel.E2_COMPUTATIONAL, source=f"{result.engine} {result.engine_version or 'unknown'}", payload=payload); m.evidence.append(ev)
        m.gates.append(GateResult("GATE-DOCKING", "DOCK-RUN-001", GateStatus.PASS, "docking engine completed successfully", evidence_ids=(ev.evidence_id,), diagnostics={"best_affinity_kcal_mol": result.best_affinity_kcal_mol})); return m
