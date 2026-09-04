from __future__ import annotations

from typing import Any
import uuid

from research_os.combustion import CombustionLab
from research_os.core.provenance import provenance_from_mapping
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.engines.propulsion import IdealIsentropicNozzleEngine, IdealNozzleRequest
from research_os.knowledge.claims import ScientificClaim, claim_from_run
from research_os.labs.base import Lab
from research_os.proof.engine import ProofEngine
from research_os.proof.rules import Rule
from research_os.propulsion.rules import propulsion_rules


class PropulsionLab(Lab):
    """Cross-lab propulsion calculation built on CombustionLab evidence.

    This first protocol implements only an ideal isentropic kinetic model. It
    will not synthesize missing gamma/MW values or fall back to the historical
    sqrt(energy/mass) heuristic.
    """

    name = "PropulsionLab"

    def __init__(self, combustion_lab: CombustionLab | None = None, nozzle_engine=None):
        self.combustion_lab = combustion_lab or CombustionLab()
        self.nozzle_engine = nozzle_engine or IdealIsentropicNozzleEngine()

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {"combustion": dict(raw.get("combustion") or {}), "exit_pressure_pa": float(raw.get("exit_pressure_pa", 101325.0)), "nozzle_efficiency": float(raw.get("nozzle_efficiency", 1.0)), "provenance": dict(raw.get("provenance") or {})}

    def rules(self) -> list[Rule]:
        return propulsion_rules()

    def run(self, raw: dict[str, Any], experiment: str = "ideal_nozzle_from_combustion") -> RunManifest:
        normalized = self.normalize(raw)
        manifest = RunManifest(lab=self.name, experiment=experiment, inputs=normalized, config={"nozzle_model": type(self.nozzle_engine).__name__, "nozzle_model_version": self.nozzle_engine.version})
        provenance = provenance_from_mapping(normalized.get("provenance"), default_source_id="propulsion-input")
        manifest.provenance.append(provenance)
        ProofEngine().evaluate(manifest, self.rules())
        if not manifest.passed: return manifest

        combustion_run = self.combustion_lab.run(normalized["combustion"], experiment="propulsion_chamber_equilibrium")
        if not combustion_run.passed:
            loss = combustion_run.first_loss
            manifest.gates.append(GateResult("GATE-PROP-COMBUSTION", "PROP-COMB-001", loss.status if loss else GateStatus.FAIL, "upstream combustion calculation did not pass", diagnostics={"nested_run_id": combustion_run.run_id, "nested_first_loss": loss.rule_id if loss else None}))
            return manifest

        comb_ev = next((e for e in reversed(combustion_run.evidence) if e.kind == "combustion_equilibrium_simulation"), None)
        if comb_ev is None:
            manifest.gates.append(GateResult("GATE-PROP-COMBUSTION", "PROP-COMB-002", GateStatus.INSUFFICIENT_EVIDENCE, "upstream run passed but no E3 combustion evidence was found"))
            return manifest

        payload = comb_ev.payload
        gamma, mw = payload.get("gamma"), payload.get("mean_molecular_weight")
        chamber_t, chamber_p = payload.get("adiabatic_temperature_k"), payload.get("pressure_pa")
        missing = [name for name, value in {"gamma": gamma, "mean_molecular_weight": mw, "adiabatic_temperature_k": chamber_t, "pressure_pa": chamber_p}.items() if value is None]
        if missing:
            manifest.gates.append(GateResult("GATE-PROP-THERMO", "PROP-THERMO-001", GateStatus.INSUFFICIENT_EVIDENCE, "combustion evidence lacks thermodynamic fields required by nozzle model", diagnostics={"missing": missing, "nested_run_id": combustion_run.run_id}))
            return manifest
        if normalized["exit_pressure_pa"] >= float(chamber_p):
            manifest.gates.append(GateResult("GATE-PROP-THERMO", "PROP-THERMO-002", GateStatus.FAIL, "exit pressure must be below chamber pressure for expansion model", diagnostics={"exit_pressure_pa": normalized["exit_pressure_pa"], "chamber_pressure_pa": chamber_p}))
            return manifest

        try:
            result = self.nozzle_engine.calculate(IdealNozzleRequest(chamber_temperature_k=float(chamber_t), chamber_pressure_pa=float(chamber_p), exit_pressure_pa=normalized["exit_pressure_pa"], gamma=float(gamma), mean_molecular_weight_kg_kmol=float(mw), nozzle_efficiency=normalized["nozzle_efficiency"]))
        except Exception as exc:
            manifest.gates.append(GateResult("GATE-PROP-MODEL", "PROP-MODEL-001", GateStatus.FAIL, "ideal nozzle model failed", diagnostics={"error_type": type(exc).__name__, "error": str(exc)}))
            return manifest

        evidence = Evidence(
            evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", kind="ideal_propulsion_performance", level=EvidenceLevel.E3_PHYSICS,
            source="CombustionLab E3 + ideal isentropic nozzle relation", provenance_ids=(provenance.provenance_id,),
            payload={**result.to_dict(), "upstream_combustion_run_id": combustion_run.run_id, "upstream_combustion_evidence_id": comb_ev.evidence_id,
                     "limitations": ["kinetic-only ideal nozzle model; pressure thrust and geometry are not included", "does not model frozen chemistry, two-phase flow, heat loss, boundary layers, or hardware durability", "not an experimental engine-performance measurement"]},
        )
        manifest.evidence.append(evidence)
        manifest.gates.extend([
            GateResult("GATE-PROP-COMBUSTION", "PROP-COMB-001", GateStatus.PASS, "upstream combustion run passed", diagnostics={"nested_run_id": combustion_run.run_id}),
            GateResult("GATE-PROP-THERMO", "PROP-THERMO-001", GateStatus.PASS, "required thermodynamic properties available", evidence_ids=(comb_ev.evidence_id,)),
            GateResult("GATE-PROP-MODEL", "PROP-MODEL-001", GateStatus.PASS, "ideal nozzle calculation completed", evidence_ids=(evidence.evidence_id,)),
        ])
        return manifest

    def ideal_performance_claim(self, run: RunManifest) -> ScientificClaim:
        return claim_from_run(run, "Ideal kinetic nozzle performance was calculated from physics-backed combustion evidence under the recorded assumptions.", minimum_evidence_level=EvidenceLevel.E3_PHYSICS, limitations=("This is not a full engine design, thrust measurement, or experimental validation.",))
