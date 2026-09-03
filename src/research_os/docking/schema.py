from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any
from research_os.core.hashing import sha256_json

@dataclass(frozen=True)
class GridBox:
    center_x: float
    center_y: float
    center_z: float
    size_x: float
    size_y: float
    size_z: float
    def to_dict(self) -> dict[str, float]: return asdict(self)
    def validate(self) -> None:
        if any(not math.isfinite(float(value)) or float(value) <= 0 for value in (self.size_x, self.size_y, self.size_z)):
            raise ValueError("grid sizes must be positive")
    @property
    def grid_hash(self) -> str: return sha256_json(self.to_dict())

@dataclass(frozen=True)
class DockingRequest:
    receptor_path: str
    ligand_path: str
    grid: GridBox
    exhaustiveness: int = 8
    cpu: int = 1
    seed: int = 42
    output_path: str | None = None
    target_id: str | None = None
    species: str | None = None
    role: str | None = None
    receptor_metadata: dict[str, Any] | None = None
    protocol_id: str = "autodock-vina.docking.v1"
    timeout: float = 300.0
    prepared_ligand_manifest: dict[str, Any] | None = None
    prepared_receptor_manifest: dict[str, Any] | None = None

@dataclass(frozen=True)
class DockingResult:
    best_affinity_kcal_mol: float | None
    output_path: str | None
    stdout: str
    stderr: str
    returncode: int
    engine: str
    engine_version: str | None
    command: tuple[str, ...]
    status: str = "SUPPORTED_AND_EXECUTED"
    receptor_sha256: str | None = None
    ligand_sha256: str | None = None
    output_sha256: str | None = None
    log_sha256: str | None = None
    grid_hash: str | None = None
    target_id: str | None = None
    species: str | None = None
    protocol_id: str | None = None
    timed_out: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)
