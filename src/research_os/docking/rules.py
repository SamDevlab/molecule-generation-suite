from __future__ import annotations
from pathlib import Path
from research_os.core.types import GateResult, GateStatus
from research_os.proof.rules import Rule, require_fields

def docking_rules(engine) -> list[Rule]:
    rules = [require_fields("DOCK-INPUT-001", ("receptor_path", "ligand_path", "grid"))]
    def files(ctx, evidence):
        missing = [key for key in ("receptor_path", "ligand_path") if not Path(ctx[key]).is_file()]
        if missing:
            return GateResult("GATE-ARTIFACT", "DOCK-FILE-001", GateStatus.FAIL, "required docking artifacts missing", diagnostics={"missing": missing})
        return GateResult("GATE-ARTIFACT", "DOCK-FILE-001", GateStatus.PASS, "receptor and ligand artifacts exist")
    def grid(ctx, evidence):
        g = ctx["grid"]; sizes = [float(g[k]) for k in ("size_x", "size_y", "size_z")]
        if any(v <= 0 for v in sizes):
            return GateResult("GATE-CONFIG", "DOCK-GRID-001", GateStatus.FAIL, "grid sizes must be positive", diagnostics={"sizes": sizes})
        return GateResult("GATE-CONFIG", "DOCK-GRID-001", GateStatus.PASS, "grid box structurally valid")
    def engine_available(ctx, evidence):
        if not engine.available:
            return GateResult("GATE-ENGINE", "DOCK-ENGINE-001", GateStatus.INDETERMINATE, "Vina engine unavailable; docking not executed")
        return GateResult("GATE-ENGINE", "DOCK-ENGINE-001", GateStatus.PASS, "Vina engine available", diagnostics={"version": engine.version})
    rules.extend([Rule("DOCK-FILE-001", "Require receptor and ligand files", files), Rule("DOCK-GRID-001", "Require a positive per-run docking grid", grid), Rule("DOCK-ENGINE-001", "Require an available docking engine", engine_available)])
    return rules
