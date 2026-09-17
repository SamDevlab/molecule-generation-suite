from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
@dataclass(frozen=True)
class PharmaRequest:
    smiles: str
    name: str | None = None
    molecule_id: str | None = None
    docking: dict[str, Any] | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
