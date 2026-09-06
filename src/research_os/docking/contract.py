"""Explicit pre-execution contract for reproducible computational docking."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
import re
from typing import Any, Mapping

from research_os.core.hashing import sha256_json
from .schema import GridBox


@dataclass(frozen=True)
class DockingExecutionContract:
    protocol_id: str
    engine_id: str
    receptor_path: str
    ligand_path: str
    grid: GridBox
    seed: int
    exhaustiveness: int
    cpu: int
    num_modes: int
    timeout_seconds: float
    target_id: str | None = None
    species: str | None = None
    receptor_structure_id: str | None = None
    receptor_source_id: str | None = None
    receptor_sha256: str | None = None
    ligand_source_id: str | None = None
    ligand_sha256: str | None = None
    evidence_ceiling: str = "E2_COMPUTATIONAL"
    limitations: tuple[str, ...] = ("docking is computational evidence and not experimental binding affinity",)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, engine_id: str = "autodock-vina") -> "DockingExecutionContract":
        grid = raw.get("grid")
        if not isinstance(grid, Mapping):
            raise ValueError("docking contract requires a grid mapping")
        return cls(
            protocol_id=str(raw.get("protocol_id") or ""), engine_id=engine_id,
            receptor_path=str(raw.get("receptor_path") or ""), ligand_path=str(raw.get("ligand_path") or ""), grid=GridBox(**{key: float(grid[key]) for key in ("center_x", "center_y", "center_z", "size_x", "size_y", "size_z")}),
            seed=int(raw.get("seed", 0)), exhaustiveness=int(raw.get("exhaustiveness", 0)), cpu=int(raw.get("cpu", 0)), num_modes=int(raw.get("num_modes", 0)), timeout_seconds=float(raw.get("timeout", 0.0)), target_id=raw.get("target_id"), species=raw.get("species"), receptor_structure_id=(raw.get("receptor_metadata") or {}).get("structure_id"), receptor_source_id=(raw.get("receptor_metadata") or {}).get("source_id"), receptor_sha256=(raw.get("receptor_metadata") or {}).get("sha256"), ligand_source_id=(raw.get("prepared_ligand_manifest") or {}).get("source_id"), ligand_sha256=(raw.get("prepared_ligand_manifest") or {}).get("input_sha256"), metadata={"prepared_ligand": bool(raw.get("prepared_ligand_manifest")), "prepared_receptor": bool(raw.get("prepared_receptor_manifest"))},
        )

    def validate(self, *, strict_provenance: bool = False, validate_grid: bool = True) -> None:
        if not self.protocol_id or not re.fullmatch(r"[A-Za-z0-9_.:-]+", self.protocol_id):
            raise ValueError("protocol_id must be explicit and path-safe")
        if self.engine_id != "autodock-vina":
            raise ValueError("docking contract engine_id must identify AutoDock Vina")
        if not self.receptor_path or not self.ligand_path:
            raise ValueError("receptor_path and ligand_path are required")
        if validate_grid:
            self.grid.validate()
        if self.exhaustiveness < 1 or self.cpu < 1 or self.num_modes < 1 or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("docking execution limits must be positive")
        if not self.evidence_ceiling == "E2_COMPUTATIONAL":
            raise ValueError("docking evidence ceiling is fixed at E2_COMPUTATIONAL")
        for name, value in (("receptor_sha256", self.receptor_sha256), ("ligand_sha256", self.ligand_sha256)):
            if value is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", str(value)):
                raise ValueError(f"{name} must be a SHA-256 digest when supplied")
        if strict_provenance and (not self.target_id or not self.species or not self.receptor_structure_id or not self.receptor_source_id or not self.receptor_sha256):
            raise ValueError("strict docking contract requires target, species, receptor identity, source and hash")

    @property
    def contract_hash(self) -> str:
        return sha256_json(self._payload())

    def _payload(self) -> dict[str, Any]:
        data = asdict(self)
        data["grid"] = self.grid.to_dict()
        data["limitations"] = list(self.limitations)
        data["metadata"] = dict(self.metadata)
        return data

    def to_dict(self) -> dict[str, Any]:
        data = self._payload()
        data["contract_hash"] = self.contract_hash
        return data
