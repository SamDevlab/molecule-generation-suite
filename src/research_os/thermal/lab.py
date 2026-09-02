from __future__ import annotations

from typing import Any
import uuid

from research_os.core.provenance import provenance_from_mapping
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.knowledge.claims import ScientificClaim, claim_from_run
from research_os.labs.base import Lab
from research_os.proof.engine import ProofEngine
from research_os.proof.rules import Rule
from research_os.thermal.models import PlanarConductionRequest, planar_conduction
from research_os.thermal.rules import thermal_rules


class ThermalLab(Lab):
    """1-D steady planar Fourier conduction with explicit limitations."""

    name = "ThermalLab"

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "hot_temperature_k": float(raw["hot_temperature_k"]) if raw.get("hot_temperature_k") is not None else None,
            "cold_temperature_k": float(raw["cold_temperature_k"]) if raw.get("cold_temperature_k") is not None else None,
            "conductivity_w_mk": float(raw["conductivity_w_mk"]) if raw.get("conductivity_w_mk") is not None else None,
            "thickness_m": float(raw["thickness_m"]) if raw.get("thickness_m") is not None else None,
            "area_m2": float(raw.get("area_m2", 1.0)),
            "provenance": dict(raw.get("provenance") or {}),
        }

    def rules(self) -> list[Rule]:
        return thermal_rules()

    def run(self, raw: dict[str, Any], experiment: str = "steady_planar_conduction") -> RunManifest:
        normalized = self.normalize(raw)
        manifest = RunManifest(lab=self.name, experiment=experiment, inputs=normalized, config={"model": "fourier_1d_steady_planar_constant_k", "model_version": "1"})
        provenance = provenance_from_mapping(normalized.get("provenance"), default_source_id="thermal-input")
        manifest.provenance.append(provenance)
        ProofEngine().evaluate(manifest, self.rules())
        if not manifest.passed:
            return manifest
        try:
            result = planar_conduction(PlanarConductionRequest(
                hot_temperature_k=normalized["hot_temperature_k"],
                cold_temperature_k=normalized["cold_temperature_k"],
                conductivity_w_mk=normalized["conductivity_w_mk"],
                thickness_m=normalized["thickness_m"], area_m2=normalized["area_m2"],
            ))
        except Exception as exc:
            manifest.gates.append(GateResult("GATE-THERM-MODEL", "THERM-MODEL-001", GateStatus.FAIL, "thermal model failed", diagnostics={"error_type": type(exc).__name__, "error": str(exc)}))
            return manifest

        ev = Evidence(
            evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", kind="steady_planar_conduction",
            level=EvidenceLevel.E3_PHYSICS, source="Fourier 1-D steady planar conduction",
            provenance_ids=(provenance.provenance_id,),
            payload={**result.to_dict(),
                     "assumptions": ["steady state", "one-dimensional planar conduction", "constant thermal conductivity", "no internal heat generation"],
                     "limitations": ["does not include convection or radiation", "does not include thermal contact resistance", "does not include transient response or temperature-dependent conductivity"]},
        )
        manifest.evidence.append(ev)
        manifest.gates.append(GateResult("GATE-THERM-MODEL", "THERM-MODEL-001", GateStatus.PASS, "Fourier conduction calculation completed", evidence_ids=(ev.evidence_id,)))
        return manifest

    def conduction_claim(self, run: RunManifest) -> ScientificClaim:
        return claim_from_run(
            run,
            "Steady one-dimensional conductive heat transfer was calculated under the recorded Fourier-model assumptions.",
            minimum_evidence_level=EvidenceLevel.E3_PHYSICS,
            limitations=("This does not establish real hardware wall temperature or survivability without omitted heat-transfer modes and material data.",),
        )
