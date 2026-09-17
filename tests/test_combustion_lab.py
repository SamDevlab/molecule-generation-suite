from research_os.combustion import CombustionLab
from research_os.core.types import GateStatus
from research_os.engines.combustion import EquilibriumResult


class FakeEngine:
    available = True
    version = "test-1"
    def simulate_equilibrium(self, request):
        return EquilibriumResult(adiabatic_temperature_k=2200.0, pressure_pa=request.pressure_pa, mean_molecular_weight=27.0, major_species_mole_fractions={"N2": 0.7, "H2O": 0.18, "CO2": 0.09}, engine="FakePhysicsEngine", engine_version=self.version, mechanism=request.mechanism)


class MissingEngine:
    available = False
    version = None
    def simulate_equilibrium(self, request):
        raise AssertionError("should not run")


def base_request():
    return {"fuel": "CH4:1", "oxidizer": "O2:0.21,N2:0.79", "equivalence_ratio": 1.0, "temperature_k": 300.0, "pressure_pa": 101325.0}


def test_combustion_result_requires_physics_engine_and_creates_e3_evidence():
    run = CombustionLab(engine=FakeEngine()).run(base_request())
    assert run.passed
    assert run.evidence[-1].level.value == "E3_PHYSICS"
    assert run.evidence[-1].payload["adiabatic_temperature_k"] == 2200.0
    assert run.gates[-1].rule_id == "COMB-SIM-001"


def test_missing_physics_engine_is_indeterminate_not_pass():
    run = CombustionLab(engine=MissingEngine()).run(base_request())
    assert not run.passed
    assert run.first_loss.rule_id == "COMB-ENGINE-001"
    assert run.first_loss.status == GateStatus.INDETERMINATE


def test_invalid_absolute_temperature_fails_before_engine():
    request = base_request(); request["temperature_k"] = 0
    run = CombustionLab(engine=FakeEngine()).run(request)
    assert not run.passed
    assert run.first_loss.rule_id == "COMB-COND-001"
