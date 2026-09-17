import pytest

from research_os.engines import EngineRegistry, run_cantera_reference_case
from research_os.engines.cantera import CanteraEquilibriumEngine


@pytest.mark.reference
def test_cantera_reference_executes_when_dependency_is_installed():
    """Require both discovery and a real Cantera reference execution."""
    discovery = EngineRegistry().get_engine("cantera")
    if not discovery.available:
        pytest.skip("Cantera is not installed in this capability environment")

    assert discovery.status == "AVAILABLE_BUT_NOT_EXECUTED"

    adapter = CanteraEquilibriumEngine()
    assert adapter.available
    case = run_cantera_reference_case(adapter)

    assert case.result_status == "SUPPORTED_AND_EXECUTED", case.to_dict()
    assert case.valid
    assert case.last_validated_at is not None
    assert case.result["engine"] == "Cantera"
    assert case.result["engine_version"] == discovery.version
    assert case.result["adiabatic_temperature_k"] > 0
    assert case.result["pressure_pa"] > 0
    assert case.result["mean_molecular_weight"] > 0
    assert case.result["gamma"] > 1
