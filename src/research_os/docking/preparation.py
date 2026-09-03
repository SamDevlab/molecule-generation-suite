"""Explicit ligand/receptor preparation boundaries for docking."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import uuid

from research_os.core.hashing import sha256_file, sha256_json
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.engines.openbabel import OpenBabelEngine


@dataclass(frozen=True)
class LigandPreparationRequest:
    candidate_id: str
    input_path: str
    output_path: str
    output_format: str = "pdbqt"
    protonation_assumptions: tuple[str, ...] = ()
    generate_3d: bool = True
    charges: str | None = None
    seed: int | None = None
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class LigandPreparationManifest:
    candidate_id: str
    input_path: str
    output_path: str
    input_sha256: str | None
    output_sha256: str | None
    engine_id: str
    engine_version: str | None
    protocol_id: str
    status: str
    assumptions: tuple[str, ...] = ()
    manifest_hash: str | None = None

    def __post_init__(self) -> None:
        if self.manifest_hash is None:
            object.__setattr__(self, "manifest_hash", sha256_json({key: getattr(self, key) for key in ("candidate_id", "input_path", "output_path", "input_sha256", "output_sha256", "engine_id", "engine_version", "protocol_id", "status", "assumptions")}))
    def to_dict(self) -> dict[str, Any]: return asdict(self)


def prepare_ligand(request: LigandPreparationRequest, engine: OpenBabelEngine | None = None, *, timeout: float = 60.0) -> LigandPreparationManifest:
    adapter = engine or OpenBabelEngine()
    source = Path(request.input_path)
    input_hash = sha256_file(source) if source.is_file() else None
    if not adapter.available or input_hash is None:
        return LigandPreparationManifest(request.candidate_id, request.input_path, request.output_path, input_hash, None, "openbabel", adapter.version, "openbabel.ligand-preparation.v1", "INDETERMINATE", request.protonation_assumptions)
    try:
        result = adapter.convert(source, request.output_path, options=request.options, timeout=timeout, protocol_id="openbabel.ligand-preparation.v1")
    except (OSError, RuntimeError):
        return LigandPreparationManifest(request.candidate_id, request.input_path, request.output_path, input_hash, None, "openbabel", adapter.version, "openbabel.ligand-preparation.v1", "INDETERMINATE", request.protonation_assumptions)
    output_hash = sha256_file(request.output_path) if Path(request.output_path).is_file() else None
    return LigandPreparationManifest(request.candidate_id, request.input_path, request.output_path, input_hash, output_hash, "openbabel", result.engine_version, result.protocol_id or "openbabel.ligand-preparation.v1", "SUPPORTED_AND_EXECUTED" if result.returncode == 0 and output_hash else "INDETERMINATE", request.protonation_assumptions)


@dataclass(frozen=True)
class ReceptorPreparationRequest:
    target_id: str
    species: str
    role: str
    structure_id: str
    source: str
    input_path: str
    output_path: str
    resolution_angstrom: float | None = None
    method: str | None = None
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReceptorPreparationManifest:
    target_id: str
    species: str
    role: str
    structure_id: str
    source: str
    input_sha256: str | None
    prepared_sha256: str | None
    output_path: str
    engine_id: str
    engine_version: str | None
    protocol_id: str
    status: str
    metadata: dict[str, Any]
    manifest_hash: str | None = None

    def __post_init__(self) -> None:
        if self.manifest_hash is None:
            object.__setattr__(self, "manifest_hash", sha256_json({key: getattr(self, key) for key in ("target_id", "species", "role", "structure_id", "source", "input_sha256", "prepared_sha256", "output_path", "engine_id", "engine_version", "protocol_id", "status", "metadata")}))
    def to_dict(self) -> dict[str, Any]: return asdict(self)


def prepare_receptor(request: ReceptorPreparationRequest, engine: OpenBabelEngine | None = None, *, timeout: float = 120.0) -> ReceptorPreparationManifest:
    adapter = engine or OpenBabelEngine()
    source = Path(request.input_path)
    input_hash = sha256_file(source) if source.is_file() else None
    if not adapter.available or input_hash is None:
        return ReceptorPreparationManifest(request.target_id, request.species, request.role, request.structure_id, request.source, input_hash, None, request.output_path, "openbabel", adapter.version, "openbabel.receptor-preparation.v1", "INDETERMINATE", {"resolution_angstrom": request.resolution_angstrom, "method": request.method})
    try:
        result = adapter.convert(source, request.output_path, options=request.options, timeout=timeout, protocol_id="openbabel.receptor-preparation.v1")
    except (OSError, RuntimeError):
        return ReceptorPreparationManifest(request.target_id, request.species, request.role, request.structure_id, request.source, input_hash, None, request.output_path, "openbabel", adapter.version, "openbabel.receptor-preparation.v1", "INDETERMINATE", {"resolution_angstrom": request.resolution_angstrom, "method": request.method})
    output_hash = sha256_file(request.output_path) if Path(request.output_path).is_file() else None
    return ReceptorPreparationManifest(request.target_id, request.species, request.role, request.structure_id, request.source, input_hash, output_hash, request.output_path, "openbabel", result.engine_version, result.protocol_id or "openbabel.receptor-preparation.v1", "SUPPORTED_AND_EXECUTED" if result.returncode == 0 and output_hash else "INDETERMINATE", {"resolution_angstrom": request.resolution_angstrom, "method": request.method})


class LigandPreparationLab:
    name = "LigandPreparationLab"
    def __init__(self, engine: OpenBabelEngine | None = None): self.engine = engine or OpenBabelEngine()
    def run(self, raw: dict[str, Any], experiment: str = "ligand_preparation") -> RunManifest:
        manifest = RunManifest(self.name, experiment, dict(raw), config={"engine_id": "openbabel", "engine_version": self.engine.version, "protocol_id": "openbabel.ligand-preparation.v1"})
        try:
            request = LigandPreparationRequest(candidate_id=str(raw["candidate_id"]), input_path=str(raw["input_path"]), output_path=str(raw["output_path"]), output_format=str(raw.get("output_format", "pdbqt")), protonation_assumptions=tuple(raw.get("protonation_assumptions") or ()), generate_3d=bool(raw.get("generate_3d", True)), charges=raw.get("charges"), seed=raw.get("seed"), options=tuple(raw.get("options") or ()))
            result = prepare_ligand(request, self.engine)
        except (KeyError, TypeError, ValueError) as exc:
            manifest.gates.append(GateResult("GATE-LIGAND-PREP", "LIGAND-PREP-INPUT-001", GateStatus.FAIL, "invalid ligand preparation request", diagnostics={"error_type": type(exc).__name__, "error": str(exc)})); return manifest
        return _preparation_run_result(manifest, result, "ligand_preparation")


class ReceptorPreparationLab:
    name = "ReceptorPreparationLab"
    def __init__(self, engine: OpenBabelEngine | None = None): self.engine = engine or OpenBabelEngine()
    def run(self, raw: dict[str, Any], experiment: str = "receptor_preparation") -> RunManifest:
        manifest = RunManifest(self.name, experiment, dict(raw), config={"engine_id": "openbabel", "engine_version": self.engine.version, "protocol_id": "openbabel.receptor-preparation.v1"})
        try:
            request = ReceptorPreparationRequest(target_id=str(raw["target_id"]), species=str(raw["species"]), role=str(raw["role"]), structure_id=str(raw["structure_id"]), source=str(raw["source"]), input_path=str(raw["input_path"]), output_path=str(raw["output_path"]), resolution_angstrom=raw.get("resolution_angstrom"), method=raw.get("method"), options=tuple(raw.get("options") or ()))
            result = prepare_receptor(request, self.engine)
        except (KeyError, TypeError, ValueError) as exc:
            manifest.gates.append(GateResult("GATE-RECEPTOR-PREP", "RECEPTOR-PREP-INPUT-001", GateStatus.FAIL, "invalid receptor preparation request", diagnostics={"error_type": type(exc).__name__, "error": str(exc)})); return manifest
        return _preparation_run_result(manifest, result, "receptor_preparation")


def _preparation_run_result(manifest: RunManifest, result: Any, kind: str) -> RunManifest:
    if result.status != "SUPPORTED_AND_EXECUTED":
        manifest.gates.append(GateResult(f"GATE-{kind.upper()}", "OPENBABEL-PREP-001", GateStatus.INDETERMINATE, "Open Babel preparation was unavailable or did not produce a verified artifact", diagnostics={"status": result.status, "engine_id": result.engine_id})); return manifest
    evidence = Evidence(f"EVD-{uuid.uuid4().hex[:12].upper()}", kind, EvidenceLevel.E2_COMPUTATIONAL, "Open Babel", result.to_dict())
    manifest.evidence.append(evidence)
    manifest.gates.append(GateResult(f"GATE-{kind.upper()}", "OPENBABEL-PREP-001", GateStatus.PASS, "Open Babel preparation completed with content hashes", (evidence.evidence_id,)))
    return manifest
