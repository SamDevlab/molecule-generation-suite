import pytest

from research_os.molecule.legacy import LegacyFormolecularAdapter


def test_legacy_adapter_recalculates_deterministic_values():
    row = {"ID": "ethanol", "SMILES": "CCO", "Peso_Molar": 46.069, "TPSA": 20.23}
    adapter = LegacyFormolecularAdapter()
    inp = adapter.to_lab_input(row)
    assert inp["smiles"] == "CCO"
    findings = {x.legacy_column: x for x in adapter.audit_deterministic_columns(row)}
    assert findings["Peso_Molar"].recalculated_value == pytest.approx(46.069, abs=0.01)
    assert findings["TPSA"].recalculated_value == pytest.approx(20.23, abs=0.05)
