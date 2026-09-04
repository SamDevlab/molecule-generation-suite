"""Condition-aware application foundations for the v2.2 domains.

These classes are orchestration boundaries. They do not invent a simulator or
turn an input observation into E3 evidence. Scientific logic belongs in a
dedicated engine-backed Lab and must carry its conditions.
"""

from __future__ import annotations

from typing import Any

from research_os.core.types import EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.labs.base import Lab
from research_os.proof.rules import Rule


class ConditionedDomainLab(Lab):
    evidence_ceiling = EvidenceLevel.E2_COMPUTATIONAL

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {"property": raw.get("property"), "value": raw.get("value"), "unit": raw.get("unit"), "conditions": dict(raw.get("conditions") or {}), "method": raw.get("method"), "source": raw.get("source"), "uncertainty": raw.get("uncertainty")}

    def rules(self) -> list[Rule]:
        return []

    def run(self, raw: dict[str, Any], experiment: str = "conditioned_observation") -> RunManifest:
        normalized = self.normalize(raw)
        manifest = RunManifest(lab=self.name, experiment=experiment, inputs=normalized, config={"foundation": True, "evidence_ceiling": self.evidence_ceiling.value})
        if not normalized["property"] or normalized["value"] is None or not normalized["unit"]:
            manifest.gates.append(GateResult("GATE-DOMAIN-SCHEMA", "DOMAIN-SCHEMA-001", GateStatus.FAIL, "property, value and unit are required"))
            return manifest
        if not normalized["conditions"]:
            manifest.gates.append(GateResult("GATE-DOMAIN-CONDITIONS", "DOMAIN-CONDITIONS-001", GateStatus.INSUFFICIENT_EVIDENCE, "material properties require declared conditions"))
            return manifest
        if not normalized["method"]:
            manifest.gates.append(GateResult("GATE-DOMAIN-METHOD", "DOMAIN-METHOD-001", GateStatus.INDETERMINATE, "no domain method is registered; foundation does not invent a calculation"))
            return manifest
        manifest.gates.append(GateResult("GATE-DOMAIN-FOUNDATION", "DOMAIN-FOUNDATION-001", GateStatus.INDETERMINATE, "application foundation recorded input conditions but no domain engine executed"))
        return manifest


class ElectrochemistryLab(ConditionedDomainLab):
    name = "ElectrochemistryLab"


class BatteryLab(ConditionedDomainLab):
    name = "BatteryLab"


class CorrosionLab(ConditionedDomainLab):
    name = "CorrosionLab"


class MechanicsLab(ConditionedDomainLab):
    name = "MechanicsLab"


class SurfaceLab(ConditionedDomainLab):
    name = "SurfaceLab"


class TransportLab(ConditionedDomainLab):
    name = "TransportLab"


class CompositeLab(ConditionedDomainLab):
    name = "CompositeLab"


class CeramicLab(ConditionedDomainLab):
    name = "CeramicLab"


class AdditiveManufacturingLab(ConditionedDomainLab):
    name = "AdditiveManufacturingLab"


class AerospaceLab(ConditionedDomainLab):
    name = "AerospaceLab"


class AutomotiveLab(ConditionedDomainLab):
    name = "AutomotiveLab"


class EnergyLab(ConditionedDomainLab):
    name = "EnergyLab"


DOMAIN_LABS = (ElectrochemistryLab, BatteryLab, CorrosionLab, MechanicsLab, SurfaceLab, TransportLab, CompositeLab, CeramicLab, AdditiveManufacturingLab, AerospaceLab, AutomotiveLab, EnergyLab)

