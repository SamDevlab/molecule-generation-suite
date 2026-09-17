from research_os.fuel import FuelLab


def test_pure_molecular_fuel_delegates_to_molecule_lab():
    run = FuelLab().run({"name": "ethanol", "smiles": "CCO"})
    assert run.passed
    kinds = {e.kind for e in run.evidence}
    assert "fuel_composition" in kinds
    assert "fuel_component_molecular_properties" in kinds


def test_mixture_must_sum_to_one():
    run = FuelLab().run({"components": [{"name": "A", "fraction": 0.7}, {"name": "B", "fraction": 0.4}]})
    assert not run.passed
    assert run.first_loss.rule_id == "FUEL-COMP-002"


def test_named_empirical_fuel_can_exist_without_fake_smiles():
    run = FuelLab().run({"name": "Jet-A surrogate catalog entry"})
    assert run.passed
    assert len(run.evidence) == 1
    assert run.evidence[0].kind == "fuel_composition"


def test_non_physical_conditions_fail_closed():
    run = FuelLab().run({"name": "test", "conditions": {"temperature_k": -1, "pressure_pa": 101325}})
    assert not run.passed
    assert run.first_loss.rule_id == "FUEL-COND-001"
