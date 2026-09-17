from research_os.thermal import ThermalLab
from research_os.core.types import EvidenceLevel


def test_planar_conduction_produces_e3_physics_evidence():
    run = ThermalLab().run({
        "hot_temperature_k": 400.0,
        "cold_temperature_k": 300.0,
        "conductivity_w_mk": 10.0,
        "thickness_m": 0.01,
        "area_m2": 2.0,
    })
    assert run.passed
    ev = next(e for e in run.evidence if e.kind == "steady_planar_conduction")
    assert ev.level == EvidenceLevel.E3_PHYSICS
    assert abs(ev.payload["heat_flux_w_m2"] - 100000.0) < 1e-9


def test_thermal_lab_fails_closed_for_nonphysical_input():
    run = ThermalLab().run({
        "hot_temperature_k": 300.0,
        "cold_temperature_k": 400.0,
        "conductivity_w_mk": 10.0,
        "thickness_m": 0.01,
    })
    assert not run.passed
    assert run.first_loss.rule_id == "THERM-COND-001"
