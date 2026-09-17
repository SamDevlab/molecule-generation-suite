from research_os.combustion import CombustionLab
from research_os.core.types import GateStatus
from research_os.engines.combustion import EquilibriumResult
from research_os.knowledge.claims import ClaimStatus
from research_os.propulsion import PropulsionLab


class FakeCombustionEngine:
    available = True
    version = "thermo-test"
    def simulate_equilibrium(self, request):
        return EquilibriumResult(adiabatic_temperature_k=3200.0, pressure_pa=request.pressure_pa, mean_molecular_weight=22.0, major_species_mole_fractions={"H2O": 0.6, "N2": 0.4}, engine="FakePhysics", engine_version=self.version, mechanism=request.mechanism, gamma=1.22, cp_mass_j_kg_k=2100.0, cv_mass_j_kg_k=1721.3)


class MissingThermoEngine:
    available = True
    version = "old-test"
    def simulate_equilibrium(self, request):
        return EquilibriumResult(adiabatic_temperature_k=3000.0, pressure_pa=request.pressure_pa, mean_molecular_weight=24.0, major_species_mole_fractions={}, engine="OldPhysics", engine_version=self.version, mechanism=request.mechanism)


def request():
    return {"combustion": {"fuel": "H2:1", "oxidizer": "O2:1", "equivalence_ratio": 1.0, "temperature_k": 300.0, "pressure_pa": 3_000_000.0}, "exit_pressure_pa": 101325.0}


def test_propulsion_requires_e3_combustion_and_produces_limited_e3_result():
    lab = PropulsionLab(combustion_lab=CombustionLab(engine=FakeCombustionEngine()))
    run = lab.run(request())
    assert run.passed
    ev = run.evidence[-1]
    assert ev.level.value == "E3_PHYSICS"
    assert ev.payload["ideal_kinetic_specific_impulse_s"] > 0
    assert ev.payload["upstream_combustion_run_id"].startswith("RUN-")
    assert "not an experimental" in ev.payload["limitations"][-1]
    assert lab.ideal_performance_claim(run).status == ClaimStatus.SUPPORTED


def test_missing_gamma_is_insufficient_evidence_not_heuristic_fallback():
    lab = PropulsionLab(combustion_lab=CombustionLab(engine=MissingThermoEngine()))
    run = lab.run(request())
    assert not run.passed
    assert run.first_loss.rule_id == "PROP-THERMO-001"
    assert run.first_loss.status == GateStatus.INSUFFICIENT_EVIDENCE


def test_exit_pressure_must_be_below_chamber_pressure():
    raw = request(); raw["exit_pressure_pa"] = 4_000_000.0
    lab = PropulsionLab(combustion_lab=CombustionLab(engine=FakeCombustionEngine()))
    run = lab.run(raw)
    assert not run.passed
    assert run.first_loss.rule_id == "PROP-THERMO-002"
