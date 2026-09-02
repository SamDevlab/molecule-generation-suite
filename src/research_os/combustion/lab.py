from __future__ import annotations

from typing import Any
import uuid

from research_os.combustion.rules import combustion_request_rules, engine_available_rule
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.engines import CanteraEquilibriumEngine, EquilibriumRequest
from research_os.labs.base import Lab
from research_os.proof.engine import ProofEngine
from research_os.proof.rules import Rule


class CombustionLab(Lab):
    """Physics-backed combustion calculations, separate from FuelLab.

    v0 implements only adiabatic constant-pressure chemical equilibrium.
    Kinetic ignition delay, flame speed and reactor models are intentionally
    outside this first protocol.
    """

    name = "CombustionLab"

    def __init__(self, engine=None):
        self.engine = engine or CanteraEquilibriumEngine()

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {"fuel": raw.get("fuel"), "oxidizer": raw.get("oxidizer", "O2:0.21,N2:0.79"), "equivalence_ratio": float(raw.get("equivalence_ratio", 1.0)), "temperature_k": float(raw.get("temperature_k", 298.15)), "pressure_pa": float(raw.get("pressure_pa", 101325.0)), "basis": raw.get("basis", "mole"), "mechanism": raw.get("mechanism", "gri30.yaml")}

    def rules(self) -> list[Rule]:
        return [*combustion_request_rules(), engine_available_rule(self.engine)]

    def run(self, raw: dict[str, Any], experiment: str = "adiabatic_equilibrium_hp") -> RunManifest:
        normalized = self.normalize(raw)
        manifest = RunManifest(lab=self.name, experiment=experiment, inputs=normalized, config={"engine": type(self.engine).__name__, "engine_version": self.engine.version, "model": "adiabatic_chemical_equilibrium_HP"})
        ProofEngine().evaluate(manifest, self.rules())
        if not manifest.passed: return manifest
        try:
            result = self.engine.simulate_equilibrium(EquilibriumRequest(**normalized))
        except Exception as exc:
            manifest.gates.append(GateResult("GATE-PHYSICS-SIMULATION", "COMB-SIM-001", GateStatus.FAIL, "combustion physics engine execution failed", diagnostics={"error_type": type(exc).__name__, "error": str(exc)}))
            return manifest
        evidence = Evidence(evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", kind="combustion_equilibrium_simulation", level=EvidenceLevel.E3_PHYSICS, source=f"{result.engine} {result.engine_version or 'unknown'} / {result.mechanism}", payload=result.to_dict())
        manifest.evidence.append(evidence)
        manifest.gates.append(GateResult("GATE-PHYSICS-SIMULATION", "COMB-SIM-001", GateStatus.PASS, "adiabatic HP equilibrium calculation completed", evidence_ids=(evidence.evidence_id,), diagnostics={"model": result.model}))
        return manifest
