from __future__ import annotations

from typing import Any
import uuid

from research_os.core.provenance import SourceType, provenance_from_mapping
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.labs.base import Lab
from research_os.proof.engine import ProofEngine
from research_os.proof.rules import Rule
from research_os.degradation.rules import degradation_rules


class DegradationLab(Lab):
    """Evidence-first degradation/corrosion observation lab.

    This protocol does not predict corrosion rate, hydrogen embrittlement,
    oxidation life, creep damage, or fatigue from names alone. It records an
    exposure and attaches a supplied observation only when provenance and
    evidence class are explicit.
    """

    name = "DegradationLab"

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        observation = dict(raw.get("observation") or {})
        return {
            "material": raw.get("material"),
            "environment": raw.get("environment"),
            "temperature_k": float(raw["temperature_k"]) if raw.get("temperature_k") is not None else None,
            "pressure_pa": float(raw["pressure_pa"]) if raw.get("pressure_pa") is not None else None,
            "duration_s": float(raw["duration_s"]) if raw.get("duration_s") is not None else None,
            "mechanism": raw.get("mechanism"),
            "observation": observation,
            "provenance": dict(raw.get("provenance") or {}),
        }

    def rules(self) -> list[Rule]:
        return degradation_rules()

    def run(self, raw: dict[str, Any], experiment: str = "degradation_evidence") -> RunManifest:
        normalized = self.normalize(raw)
        manifest = RunManifest(lab=self.name, experiment=experiment, inputs=normalized, config={"protocol": "evidence_only_v1"})
        provenance = provenance_from_mapping(normalized.get("provenance"), default_source_id="degradation-input")
        manifest.provenance.append(provenance)
        ProofEngine().evaluate(manifest, self.rules())
        if not manifest.passed:
            return manifest

        exposure_ev = Evidence(
            evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}",
            kind="degradation_exposure_record", level=EvidenceLevel.E0_HEURISTIC,
            source="DegradationLab exposure catalog", provenance_ids=(provenance.provenance_id,),
            payload={k: normalized[k] for k in ("material", "environment", "temperature_k", "pressure_pa", "duration_s", "mechanism")},
        )
        manifest.evidence.append(exposure_ev)

        obs = normalized["observation"]
        if not obs:
            manifest.gates.append(GateResult(
                "GATE-DEG-EVIDENCE", "DEG-EVIDENCE-001", GateStatus.INSUFFICIENT_EVIDENCE,
                "exposure was recorded, but no attributable degradation observation or predictive engine was supplied",
                evidence_ids=(exposure_ev.evidence_id,),
            ))
            return manifest

        required = [key for key in ("metric", "value", "unit", "evidence_level") if obs.get(key) is None]
        if required:
            manifest.gates.append(GateResult("GATE-DEG-EVIDENCE", "DEG-EVIDENCE-001", GateStatus.FAIL, "degradation observation is incomplete", diagnostics={"missing": required}))
            return manifest
        try:
            level = EvidenceLevel(str(obs["evidence_level"]))
        except ValueError:
            manifest.gates.append(GateResult("GATE-DEG-EVIDENCE", "DEG-EVIDENCE-001", GateStatus.FAIL, "invalid observation evidence_level", diagnostics={"value": obs.get("evidence_level")}))
            return manifest
        if level in {EvidenceLevel.E4_CURATED_EXPERIMENTAL, EvidenceLevel.E5_VALIDATED_EXPERIMENTAL} and provenance.source_type not in {SourceType.PUBLICATION, SourceType.DATASET, SourceType.DATABASE, SourceType.EXPERIMENT}:
            manifest.gates.append(GateResult(
                "GATE-DEG-EVIDENCE", "DEG-EVIDENCE-002", GateStatus.INSUFFICIENT_EVIDENCE,
                "experimental evidence level requires attributable publication/dataset/database/experiment provenance",
                diagnostics={"source_type": provenance.source_type.value, "requested_level": level.value},
            ))
            return manifest

        obs_ev = Evidence(
            evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", kind="degradation_observation",
            level=level, source=str(obs.get("source") or provenance.source_id), provenance_ids=(provenance.provenance_id,),
            payload={"metric": obs["metric"], "value": float(obs["value"]), "unit": str(obs["unit"]), "conditions": dict(obs.get("conditions") or {}), "notes": obs.get("notes")},
        )
        manifest.evidence.append(obs_ev)
        manifest.gates.extend([
            GateResult("GATE-DEG-EVIDENCE", "DEG-EVIDENCE-001", GateStatus.PASS, "attributable degradation observation recorded", evidence_ids=(obs_ev.evidence_id,)),
            GateResult("GATE-DEG-EVIDENCE", "DEG-EVIDENCE-002", GateStatus.PASS, "evidence/provenance compatibility check passed", evidence_ids=(obs_ev.evidence_id,)),
        ])
        return manifest
