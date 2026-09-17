"""Registry for engine reference cases; validation is explicit and auditable."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Iterable, Mapping

from research_os.engines.combustion import EquilibriumRequest
from research_os.engines.manifest import EngineReferenceCase, EngineStatus


class EngineReferenceRegistry:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root is not None else None
        self._cases: dict[str, EngineReferenceCase] = {}

    def register(self, case: EngineReferenceCase) -> EngineReferenceCase:
        self._cases[case.reference_id] = case
        return case

    def get(self, reference_id: str) -> EngineReferenceCase:
        return self._cases[reference_id]

    def list(self, engine_id: str | None = None) -> list[EngineReferenceCase]:
        return [case for case in self._cases.values() if engine_id is None or case.engine_id == engine_id]

    def save(self) -> None:
        if self.root is None:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "reference_cases.json").write_text(json.dumps([case.to_dict() for case in self._cases.values()], indent=2, sort_keys=True), encoding="utf-8")

    def load(self) -> list[EngineReferenceCase]:
        if self.root is None or not (self.root / "reference_cases.json").is_file():
            return []
        raw = json.loads((self.root / "reference_cases.json").read_text(encoding="utf-8"))
        for item in raw if isinstance(raw, list) else ():
            self.register(EngineReferenceCase(**item))
        return self.list()

    def verify(self) -> bool:
        return all(case.valid for case in self._cases.values())


def reference_cases_for(engine_ids: Iterable[str]) -> tuple[EngineReferenceCase, ...]:
    """Return declared, not executed, reference boundaries for an engine set."""
    return tuple(EngineReferenceCase(f"REF-{engine_id}-V17", engine_id, f"{engine_id}.reference.v1", result_status="AVAILABLE_BUT_NOT_EXECUTED") for engine_id in engine_ids)


def run_cantera_reference_case(engine: Any | None = None, *, environment_id: str | None = None) -> EngineReferenceCase:
    """Execute a tiny real Cantera reference only when Cantera is available."""
    from research_os.engines.cantera import CanteraEquilibriumEngine
    adapter = engine or CanteraEquilibriumEngine()
    request = EquilibriumRequest("CH4:1", "O2:0.21,N2:0.79", 1.0, 300.0, 101325.0, "mole", "gri30.yaml")
    expected = {"temperature_positive": True, "pressure_positive": True, "gamma_gt_one": True, "finite_thermo": True}
    if not adapter.available:
        return EngineReferenceCase("REF-cantera-equilibrium-v1", "cantera", request.protocol_id, request.__dict__, expected, {"relative": 1e-8}, "Cantera gri30 reference boundary", None, environment_id, EngineStatus.INDETERMINATE)
    try:
        result = adapter.simulate_equilibrium(request)
        values = result.to_dict()
        checks = {"temperature_positive": values["adiabatic_temperature_k"] > 0, "pressure_positive": values["pressure_pa"] > 0, "gamma_gt_one": values.get("gamma") is not None and values["gamma"] > 1, "finite_thermo": all(isfinite(float(values[name])) for name in ("adiabatic_temperature_k", "pressure_pa", "mean_molecular_weight"))}
        passed = all(checks.values())
        return EngineReferenceCase("REF-cantera-equilibrium-v1", "cantera", request.protocol_id, request.__dict__, expected, {"relative": 1e-8}, "Cantera gri30 reference boundary", datetime.now(timezone.utc).isoformat(), environment_id, EngineStatus.SUPPORTED_AND_EXECUTED if passed else EngineStatus.EXECUTION_FAILED, result=values)
    except Exception as exc:
        return EngineReferenceCase("REF-cantera-equilibrium-v1", "cantera", request.protocol_id, request.__dict__, expected, {"relative": 1e-8}, "Cantera gri30 reference boundary", datetime.now(timezone.utc).isoformat(), environment_id, EngineStatus.INDETERMINATE, result={"error_type": type(exc).__name__, "error": str(exc)})
