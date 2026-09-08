import pytest

from research_os.engines import EngineRegistry, run_cantera_reference_case


@pytest.mark.reference
def test_cantera_reference_executes_when_dependency_is_installed():
    """Require a real reference execution whenever the Cantera extra is present."""
    engine = EngineRegistry().get_engine("cantera")
    if not engine.available:
        pytest.skip("Cantera is not installed in this capability environment")

    case = run_cantera_reference_case(engine)

    assert case.result_status == "SUPPORTED_AND_EXECUTED", case.to_dict()
    assert case.valid
    assert case.last_validated_at is not None
    assert case.result["adiabatic_temperature_k"] > 0
    assert case.result["pressure_pa"] > 0
    assert case.result["mean_molecular_weight"] > 0
    assert case.result["gamma"] > 1
