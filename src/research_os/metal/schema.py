from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from research_os.core.hashing import sha256_json
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


@dataclass(frozen=True)
class MaterialFeatureSchema:
    schema_id: str
    feature_names: tuple[str, ...]
    fraction_basis: str
    implementation: str
    implementation_version: str | None
    limitations: tuple[str, ...] = ()
    schema_hash: str | None = None

    def __post_init__(self) -> None:
        if self.fraction_basis not in {"atomic", "mass"}:
            raise ValueError("material feature schema requires an explicit atomic or mass basis")
        if self.schema_hash is None:
            object.__setattr__(self, "schema_hash", sha256_json({"schema_id": self.schema_id, "feature_names": self.feature_names, "fraction_basis": self.fraction_basis, "implementation": self.implementation, "implementation_version": self.implementation_version, "limitations": self.limitations}))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_id": self.schema_id, "feature_names": list(self.feature_names), "fraction_basis": self.fraction_basis, "implementation": self.implementation, "implementation_version": self.implementation_version, "limitations": list(self.limitations), "schema_hash": self.schema_hash}
