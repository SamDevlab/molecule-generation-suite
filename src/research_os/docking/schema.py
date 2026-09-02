from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

@dataclass(frozen=True)
class GridBox:
    center_x: float
    center_y: float
    center_z: float
    size_x: float
    size_y: float
    size_z: float
    def to_dict(self) -> dict[str, float]: return asdict(self)

@dataclass(frozen=True)
class DockingRequest:
    receptor_path: str
    ligand_path: str
    grid: GridBox
    exhaustiveness: int = 8
    cpu: int = 1
    seed: int = 42
    output_path: str | None = None

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
    def to_dict(self) -> dict[str, Any]: return asdict(self)
