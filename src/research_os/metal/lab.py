from __future__ import annotations

from typing import Any
import math
import uuid

from research_os.core.provenance import provenance_from_mapping
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.engines.calphad import CalphadDatabaseUnavailableError, CalphadRequest, UnavailableCalphadEngine
from research_os.labs.base import Lab
from research_os.metal.features import (
    MetalFeatureRequest,
    MetalFeatureUnavailableError,
    UnavailableMetalFeatureEngine,
)
from research_os.metal.rules import metal_rules
from research_os.metal.schema import AlloyComponent, MaterialFeatureSchema, MetalRecord
from research_os.proof.engine import ProofEngine


R_J_MOL_K = 8.31446261815324


class MetalLab(Lab):
    """Composition-first metallurgy: composition -> processing -> microstructure -> properties."""

    name = "MetalLab"

    def __init__(self, calphad_engine=None, feature_engine=None):
        self.calphad_engine = calphad_engine or UnavailableCalphadEngine()
        self.feature_engine = feature_engine or UnavailableMetalFeatureEngine()

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        raw_basis = str(raw.get("fraction_basis", "atomic")).strip().lower()
        percent = raw_basis in {"at%", "wt%", "atomic_percent", "mass_percent", "weight_percent"}
        basis = "atomic" if raw_basis in {"atomic", "at", "at%", "atomic_percent"} else "mass" if raw_basis in {"mass", "weight", "wt", "wt%", "mass_percent", "weight_percent"} else raw_basis
        raw_components = raw.get("components") or raw.get("composition") or {}
        iterable = [{"element": key, "fraction": value} for key, value in raw_components.items()] if isinstance(raw_components, dict) else raw_components
        items = []
        for item in iterable:
            fraction = float(item.get("fraction", item.get("value")))
            items.append({"element": str(item.get("element")).strip(), "fraction": fraction / 100.0 if percent else fraction})
        items.sort(key=lambda value: value["element"])
        requested_features = raw.get("features")
        if isinstance(requested_features, str):
            requested_features = (requested_features,)
        return {
            "name": raw.get("name"),
            "components": items,
            "fraction_basis": basis,
            "processing": dict(raw.get("processing") or {}),
            "microstructure": dict(raw.get("microstructure") or {}),
            "test_conditions": dict(raw.get("test_conditions") or {}),
            "provenance": dict(raw.get("provenance") or {}),
            "calphad": dict(raw.get("calphad") or {}) if raw.get("calphad") is not None else None,
            "features": tuple(str(value) for value in requested_features) if requested_features is not None else None,
        }

    def rules(self):
        return metal_rules()

    def run(self, raw: dict[str, Any], experiment: str = "alloy_catalog") -> RunManifest:
        try:
            normalized = self.normalize(raw)
        except (TypeError, ValueError, AttributeError) as exc:
            manifest = RunManifest(lab=self.name, experiment=experiment, inputs=dict(raw))
            manifest.gates.append(GateResult("GATE-MET-INPUT", "MET-INPUT-001", GateStatus.FAIL, "invalid alloy input", diagnostics={"error_type": type(exc).__name__, "error": str(exc)}))
            return manifest

        manifest = RunManifest(lab=self.name, experiment=experiment, inputs=normalized)
        provenance = provenance_from_mapping(normalized.get("provenance"), default_source_id="metal-input")
        manifest.provenance.append(provenance)
        ProofEngine().evaluate(manifest, self.rules())
        if not manifest.passed:
            return manifest

        fractions = {component["element"]: component["fraction"] for component in normalized["components"]}
        descriptors: dict[str, Any] = {
            "component_count": len(fractions),
            "maximum_fraction": max(fractions.values()),
            "minimum_nonzero_fraction": min(value for value in fractions.values() if value > 0),
        }
        if normalized["fraction_basis"] == "atomic":
            descriptors["configurational_entropy_j_mol_k"] = -R_J_MOL_K * sum(value * math.log(value) for value in fractions.values() if value > 0)
        else:
            descriptors["configurational_entropy_j_mol_k"] = None
            descriptors["configurational_entropy_note"] = "requires atomic fractions; mass fractions were preserved without silent conversion"

        composition_evidence = Evidence(
            evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}",
            kind="normalized_alloy_composition",
            level=EvidenceLevel.E2_COMPUTATIONAL,
            source="MetalLab composition normalizer",
            provenance_ids=(provenance.provenance_id,),
            payload={"composition": fractions, "fraction_basis": normalized["fraction_basis"], "descriptors": descriptors, "processing": normalized["processing"], "microstructure": normalized["microstructure"], "test_conditions": normalized["test_conditions"]},
        )
        manifest.evidence.append(composition_evidence)

        requested_features = normalized.get("features")
        if requested_features:
            record = MetalRecord(tuple(AlloyComponent(element=key, fraction=value) for key, value in fractions.items()), normalized["fraction_basis"], normalized.get("name"), normalized["processing"], normalized["microstructure"], normalized["test_conditions"], normalized["provenance"])
            if not self.feature_engine.available:
                manifest.gates.append(GateResult("GATE-MET-FEATURE", "MET-FEATURE-001", GateStatus.INDETERMINATE, "requested matminer/pymatgen features are unavailable; no descriptors were fabricated"))
                return manifest
            try:
                feature_payload = self.feature_engine.calculate(MetalFeatureRequest(record, requested_features))
                schema = self.feature_engine.schema(MetalFeatureRequest(record, requested_features)) if hasattr(self.feature_engine, "schema") else MaterialFeatureSchema("unversioned-feature-schema", requested_features, record.fraction_basis, type(self.feature_engine).__name__, self.feature_engine.version)
            except (MetalFeatureUnavailableError, NotImplementedError, RuntimeError) as exc:
                manifest.gates.append(GateResult("GATE-MET-FEATURE", "MET-FEATURE-001", GateStatus.INDETERMINATE, "requested metal feature engine could not produce descriptors", diagnostics={"error_type": type(exc).__name__, "error": str(exc)}))
                return manifest
            feature_evidence = Evidence(evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", kind="metal_descriptors", level=EvidenceLevel.E2_COMPUTATIONAL, source=f"{type(self.feature_engine).__name__} {self.feature_engine.version or 'unknown'}", provenance_ids=(provenance.provenance_id,), payload={"requested_features": list(requested_features), "descriptors": feature_payload, "material_feature_schema": schema.to_dict(), "engine_status": "SUPPORTED_AND_EXECUTED"})
            manifest.evidence.append(feature_evidence)
            manifest.gates.append(GateResult("GATE-MET-FEATURE", "MET-FEATURE-001", GateStatus.PASS, "metal descriptors generated by configured feature engine", evidence_ids=(feature_evidence.evidence_id,)))

        calphad = normalized.get("calphad")
        if calphad is not None:
            if not self.calphad_engine.available:
                manifest.gates.append(GateResult("GATE-MET-THERMO", "MET-CALPHAD-001", GateStatus.INDETERMINATE, "CALPHAD was requested but no thermodynamic engine/database is configured; no phase-stability claim may be made", diagnostics={"engine": type(self.calphad_engine).__name__}))
                return manifest
            database = calphad.get("database")
            if not database:
                manifest.gates.append(GateResult("GATE-MET-THERMO", "MET-CALPHAD-002", GateStatus.INDETERMINATE, "CALPHAD was requested without an explicit thermodynamic database"))
                return manifest
            try:
                result = self.calphad_engine.calculate(CalphadRequest(composition=fractions, fraction_basis=normalized["fraction_basis"], temperature_k=calphad.get("temperature_k"), pressure_pa=float(calphad.get("pressure_pa", 101325.0)), database=str(database), phases=tuple(calphad.get("phases") or ())))
            except CalphadDatabaseUnavailableError as exc:
                manifest.gates.append(GateResult("GATE-MET-THERMO", "MET-CALPHAD-002", GateStatus.INDETERMINATE, "required CALPHAD database is missing; phase stability was not calculated", diagnostics={"error_type": type(exc).__name__, "error": str(exc)}))
                return manifest
            except (OSError, TypeError, ValueError, RuntimeError) as exc:
                manifest.gates.append(GateResult("GATE-MET-THERMO", "MET-CALPHAD-003", GateStatus.FAIL, "CALPHAD engine failed", diagnostics={"error_type": type(exc).__name__, "error": str(exc)}))
                return manifest
            evidence = Evidence(evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", kind="calphad_equilibrium", level=EvidenceLevel.E3_PHYSICS, source=f"{result.engine} {result.engine_version or 'unknown'} / {result.database}", provenance_ids=(provenance.provenance_id,), payload=result.to_dict())
            manifest.evidence.append(evidence)
            manifest.gates.append(GateResult("GATE-MET-THERMO", "MET-CALPHAD-003", GateStatus.PASS, "CALPHAD calculation completed", evidence_ids=(evidence.evidence_id,)))
        return manifest
