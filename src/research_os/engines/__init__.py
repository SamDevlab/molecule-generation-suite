from .cantera import CanteraEquilibriumEngine, CanteraMechanismUnavailableError, CanteraUnavailableError, MechanismManifest
from .combustion import CombustionEngine, EquilibriumRequest, EquilibriumResult
from .propulsion import IdealIsentropicNozzleEngine, IdealNozzleRequest, IdealNozzleResult
from .openbabel import OpenBabelEngine, OpenBabelResult, OpenBabelUnavailableError
from .manifest import EngineAvailability, EngineKind, EngineManifest, EngineReadiness, EngineReferenceCase, EngineStatus
from .registry import EngineRegistry
from .reference import EngineReferenceRegistry, run_cantera_reference_case
from .calphad import CalphadDatabaseManifest, CalphadDatabaseUnavailableError, CalphadEngine, CalphadRequest, CalphadResult, DatabaseManifest, PyCalphadEngine, UnavailableCalphadEngine


def __getattr__(name):
    # Keep the Vina adapter lazy: docking.schema is a package member and its
    # eager import would otherwise create a package-cycle during discovery.
    if name in {"VinaEngine", "VinaUnavailableError"}:
        from .vina import VinaEngine, VinaUnavailableError
        return {"VinaEngine": VinaEngine, "VinaUnavailableError": VinaUnavailableError}[name]
    raise AttributeError(name)

__all__ = [
    "CanteraEquilibriumEngine", "CanteraUnavailableError", "CanteraMechanismUnavailableError", "MechanismManifest", "CombustionEngine",
    "EquilibriumRequest", "EquilibriumResult", "IdealIsentropicNozzleEngine",
    "IdealNozzleRequest", "IdealNozzleResult",
    "OpenBabelEngine", "OpenBabelResult", "OpenBabelUnavailableError",
    "EngineAvailability", "EngineKind", "EngineManifest", "EngineReadiness", "EngineReferenceCase", "EngineStatus", "EngineRegistry", "EngineReferenceRegistry", "run_cantera_reference_case",
    "VinaEngine", "VinaUnavailableError", "CalphadEngine", "CalphadRequest", "CalphadResult", "CalphadDatabaseManifest", "DatabaseManifest", "PyCalphadEngine", "UnavailableCalphadEngine", "CalphadDatabaseUnavailableError",
]
