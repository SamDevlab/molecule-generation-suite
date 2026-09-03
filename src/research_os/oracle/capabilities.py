"""Lab and typed-tool capability declarations used by PlanValidator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from research_os.core.types import EvidenceLevel


_LEVEL_ORDER = {level: index for index, level in enumerate((EvidenceLevel.E0_HEURISTIC, EvidenceLevel.E1_ML, EvidenceLevel.E2_COMPUTATIONAL, EvidenceLevel.E3_PHYSICS, EvidenceLevel.E4_CURATED_EXPERIMENTAL, EvidenceLevel.E5_VALIDATED_EXPERIMENTAL))}


@dataclass(frozen=True)
class LabCapability:
    lab: str
    experiments: tuple[str, ...]
    evidence_ceiling: EvidenceLevel
    required_engines: tuple[str, ...] = ()
    required_inputs: tuple[str, ...] = ()
    side_effects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "experiments", tuple(self.experiments))
        object.__setattr__(self, "required_engines", tuple(self.required_engines))
        object.__setattr__(self, "required_inputs", tuple(self.required_inputs))
        object.__setattr__(self, "side_effects", tuple(self.side_effects))
        object.__setattr__(self, "evidence_ceiling", self.evidence_ceiling if isinstance(self.evidence_ceiling, EvidenceLevel) else EvidenceLevel(str(self.evidence_ceiling)))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_ceiling"] = self.evidence_ceiling.value
        for name in ("experiments", "required_engines", "required_inputs", "side_effects"):
            data[name] = list(data[name])
        return data


# Public plural spelling used by API clients that consume a Lab capability
# document. It remains the same typed record rather than a second schema.
LabCapabilities = LabCapability


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    capability: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    evidence_ceiling: EvidenceLevel
    side_effects: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_ceiling", self.evidence_ceiling if isinstance(self.evidence_ceiling, EvidenceLevel) else EvidenceLevel(str(self.evidence_ceiling)))
        object.__setattr__(self, "side_effects", tuple(self.side_effects))
        object.__setattr__(self, "requirements", tuple(self.requirements))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_ceiling"] = self.evidence_ceiling.value
        data["side_effects"] = list(self.side_effects)
        data["requirements"] = list(self.requirements)
        return data


class ToolRegistry:
    def __init__(self, specs: Iterable[ToolSpec] = ()):
        self._specs = {spec.tool_id: spec for spec in specs}

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.tool_id in self._specs:
            raise ValueError(f"tool already registered: {spec.tool_id}")
        self._specs[spec.tool_id] = spec
        return spec

    def get(self, tool_id: str) -> ToolSpec:
        return self._specs[tool_id]

    def list(self) -> tuple[ToolSpec, ...]:
        return tuple(self._specs.values())


TypedToolRegistry = ToolRegistry


def default_capabilities() -> tuple[LabCapability, ...]:
    return (
        LabCapability("MoleculeLab", ("deterministic_properties",), EvidenceLevel.E2_COMPUTATIONAL),
        LabCapability("FuelLab", ("fuel_catalog",), EvidenceLevel.E2_COMPUTATIONAL),
        LabCapability("CombustionLab", ("adiabatic_equilibrium_hp",), EvidenceLevel.E3_PHYSICS, ("cantera",), ("fuel", "mechanism", "temperature", "pressure")),
        LabCapability("ThermalLab", ("steady_planar_conduction",), EvidenceLevel.E2_COMPUTATIONAL),
        LabCapability("PropulsionLab", ("ideal_nozzle_from_combustion",), EvidenceLevel.E3_PHYSICS, ("cantera",), ("combustion", "chamber_temperature", "gamma", "molecular_weight")),
        LabCapability("MetalLab", ("alloy_catalog",), EvidenceLevel.E2_COMPUTATIONAL),
        LabCapability("DegradationLab", ("degradation_evidence",), EvidenceLevel.E2_COMPUTATIONAL),
        LabCapability("DockingLab", ("vina_docking",), EvidenceLevel.E2_COMPUTATIONAL, ("autodock-vina",), ("receptor", "ligand", "grid"), ("writes docking outputs",)),
        LabCapability("PharmaLab", ("virtual_screening",), EvidenceLevel.E2_COMPUTATIONAL),
        LabCapability("KnowledgeLab", ("zettel_ingestion", "moc_validation"), EvidenceLevel.E0_HEURISTIC),
    )
