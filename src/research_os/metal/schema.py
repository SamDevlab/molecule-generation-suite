from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
@dataclass(frozen=True)
class AlloyComponent:
    element: str
    fraction: float
@dataclass(frozen=True)
class MetalRecord:
    components: tuple[AlloyComponent, ...]
    fraction_basis: str
    name: str | None = None
    processing: dict[str, Any] = field(default_factory=dict)
    microstructure: dict[str, Any] = field(default_factory=dict)
    test_conditions: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
