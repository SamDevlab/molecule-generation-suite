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
    def target(ctx, evidence):
        metadata = ctx.get("receptor_metadata") or {}
        expected = metadata.get("species")
        actual = ctx.get("species")
        if expected and actual and str(expected).lower() != str(actual).lower():
            return GateResult("GATE-TARGET", "DOCK-SPECIES-001", GateStatus.FAIL, "receptor species does not match the declared target species", diagnostics={"expected": expected, "actual": actual})
        if ctx.get("require_species") and ctx.get("target_id") and not actual and not expected:
            return GateResult("GATE-TARGET", "DOCK-SPECIES-002", GateStatus.INSUFFICIENT_EVIDENCE, "target-specific docking requires explicit species metadata")
        return GateResult("GATE-TARGET", "DOCK-SPECIES-001", GateStatus.PASS, "target species metadata is consistent")
    def engine_available(ctx, evidence):
        if not engine.available:
            return GateResult("GATE-ENGINE", "DOCK-ENGINE-001", GateStatus.INDETERMINATE, "Vina engine unavailable; docking not executed")
        return GateResult("GATE-ENGINE", "DOCK-ENGINE-001", GateStatus.PASS, "Vina engine available", diagnostics={"version": engine.version})
    def preparations(ctx, evidence):
        if not ctx.get("require_preparation"):
            return GateResult("GATE-PREPARATION", "DOCK-PREP-001", GateStatus.PASS, "preparation manifests are optional for already prepared artifacts")
        missing = [name for name in ("prepared_ligand_manifest", "prepared_receptor_manifest") if not ctx.get(name)]
        if missing:
            return GateResult("GATE-PREPARATION", "DOCK-PREP-001", GateStatus.INSUFFICIENT_EVIDENCE, "docking requires attributable ligand and receptor preparation manifests", diagnostics={"missing": missing})
        bad = [name for name in ("prepared_ligand_manifest", "prepared_receptor_manifest") if (ctx.get(name) or {}).get("status") != "SUPPORTED_AND_EXECUTED"]
        if bad:
            return GateResult("GATE-PREPARATION", "DOCK-PREP-001", GateStatus.INDETERMINATE, "required preparation did not execute successfully", diagnostics={"manifests": bad})
        return GateResult("GATE-PREPARATION", "DOCK-PREP-001", GateStatus.PASS, "ligand and receptor preparation are attributable")
    rules.extend([Rule("DOCK-FILE-001", "Require receptor and ligand files", files), Rule("DOCK-GRID-001", "Require a positive per-run docking grid", grid), Rule("DOCK-SPECIES-001", "Require explicit target species consistency", target), Rule("DOCK-PREP-001", "Require attributable docking preparation when requested", preparations), Rule("DOCK-ENGINE-001", "Require an available docking engine", engine_available)])
    return rules
