from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from research_os.metal.schema import MetalRecord


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


class UnavailableMetalFeatureEngine:
    """Boundary for matminer/pymatgen descriptors until installed/configured."""

    available = False
    version = None

    def calculate(self, request: MetalFeatureRequest) -> dict[str, Any]:
        raise MetalFeatureUnavailableError("matminer/pymatgen feature engine unavailable")


class MatminerFeatureEngine:
    """Optional adapter placeholder; it never fabricates missing descriptors."""

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
        raise NotImplementedError("matminer descriptor mapping requires an explicit feature selection and versioned implementation")


class PymatgenFeatureEngine:
    """Optional adapter placeholder for composition descriptors."""

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
        raise NotImplementedError("pymatgen descriptor mapping requires an explicit feature selection and versioned implementation")
