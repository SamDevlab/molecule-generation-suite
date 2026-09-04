from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from research_os.metal.schema import MetalRecord
from research_os.metal.schema import MaterialFeatureSchema


class MetalFeatureUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class MetalFeatureRequest:
    record: MetalRecord
    requested_features: tuple[str, ...]


class MetalFeatureEngine(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def version(self) -> str | None: ...

    def calculate(self, request: MetalFeatureRequest) -> dict[str, Any]: ...

    def schema(self, request: MetalFeatureRequest) -> MaterialFeatureSchema: ...


class UnavailableMetalFeatureEngine:
    """Boundary for matminer/pymatgen descriptors until installed/configured."""

    available = False
    version = None

    def calculate(self, request: MetalFeatureRequest) -> dict[str, Any]:
        raise MetalFeatureUnavailableError("matminer/pymatgen feature engine unavailable")
    def schema(self, request: MetalFeatureRequest) -> MaterialFeatureSchema:
        raise MetalFeatureUnavailableError("material feature schema unavailable")


class MatminerFeatureEngine:
    """Optional real matminer composition adapter."""

    def __init__(self) -> None:
        try:
            import matminer  # type: ignore[import-not-found]
        except ImportError:
            self._module = None
        else:
            self._module = matminer

    @property
    def available(self) -> bool:
        return self._module is not None

    @property
    def version(self) -> str | None:
        return getattr(self._module, "__version__", None)

    def calculate(self, request: MetalFeatureRequest) -> dict[str, Any]:
        if not self.available:
            raise MetalFeatureUnavailableError("matminer feature engine unavailable")
        if request.record.fraction_basis != "atomic":
            raise MetalFeatureUnavailableError("the configured matminer composition protocol requires atomic fractions")
        try:
            from matminer.featurizers.composition import ElementProperty, Stoichiometry  # type: ignore[import-not-found]
            from pymatgen.core import Composition  # type: ignore[import-not-found]
        except ImportError as exc:
            raise MetalFeatureUnavailableError("matminer composition dependencies are unavailable") from exc
        composition = Composition({item.element: item.fraction for item in request.record.components})
        result: dict[str, Any] = {}
        requested = set(request.requested_features)
        if "stoichiometry" in requested:
            result.update({f"stoichiometry_{index}": float(value) for index, value in enumerate(Stoichiometry().featurize(composition))})
        element_property = ElementProperty.from_preset("magpie")
        labels = tuple(str(value) for value in element_property.feature_labels())
        values = element_property.featurize(composition)
        if not requested or "magpie" in requested:
            result.update({label: float(value) for label, value in zip(labels, values)})
        unknown = requested - {"stoichiometry", "magpie"}
        if unknown:
            raise MetalFeatureUnavailableError(f"no versioned matminer mapping for requested features: {sorted(unknown)}")
        return result

    def schema(self, request: MetalFeatureRequest) -> MaterialFeatureSchema:
        return MaterialFeatureSchema("matminer-magpie-v1", tuple(request.requested_features), request.record.fraction_basis, "matminer", self.version, ("descriptors are computational features, not measured material properties",))


class PymatgenFeatureEngine:
    """Optional real pymatgen composition adapter."""

    def __init__(self) -> None:
        try:
            import pymatgen  # type: ignore[import-not-found]
        except ImportError:
            self._module = None
        else:
            self._module = pymatgen

    @property
    def available(self) -> bool:
        return self._module is not None

    @property
    def version(self) -> str | None:
        return getattr(self._module, "__version__", None)

    def calculate(self, request: MetalFeatureRequest) -> dict[str, Any]:
        if not self.available:
            raise MetalFeatureUnavailableError("pymatgen feature engine unavailable")
        if request.record.fraction_basis != "atomic":
            raise MetalFeatureUnavailableError("the configured pymatgen composition protocol requires atomic fractions")
        from pymatgen.core import Composition  # type: ignore[import-not-found]
        composition = Composition({item.element: item.fraction for item in request.record.components})
        supported = {
            "formula": str(composition.formula),
            "reduced_formula": str(composition.reduced_formula),
            "num_elements": int(len(composition.elements)),
            "weight": float(composition.weight),
            "fractional_composition": {str(element): float(value) for element, value in composition.fractional_composition.items()},
        }
        requested = tuple(request.requested_features) or ("formula", "reduced_formula", "num_elements", "weight")
        unknown = [name for name in requested if name not in supported]
        if unknown:
            raise MetalFeatureUnavailableError(f"no versioned pymatgen mapping for requested features: {unknown}")
        return {name: supported[name] for name in requested}

    def schema(self, request: MetalFeatureRequest) -> MaterialFeatureSchema:
        return MaterialFeatureSchema("pymatgen-composition-v1", tuple(request.requested_features), request.record.fraction_basis, "pymatgen", self.version, ("composition descriptors do not establish phase stability or measured properties",))
