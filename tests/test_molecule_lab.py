import json

import pytest

from research_os.core.types import EvidenceLevel, GateStatus, RunLifecycle
from research_os.molecule.calculator import RDKitCalculator, RDKitUnavailableError
from research_os.molecule.features import MorganFeaturizer
from research_os.molecule.lab import MoleculeLab
from research_os.proof.engine import ProofEngine


def test_ethanol_gets_deterministic_rdkit_evidence():
    run = MoleculeLab().run({"SMILES": "CCO"})
    assert run.passed
    assert run.lifecycle == RunLifecycle.COMPLETED
    assert len(run.gates) == 2
    assert run.gates[-1].status == GateStatus.PASS
    assert len(run.evidence) == 1
    ev = run.evidence[0]
    assert ev.level == EvidenceLevel.E2_COMPUTATIONAL
    assert ev.payload["canonical_smiles"] == "CCO"
    assert ev.payload["molecular_weight"] == pytest.approx(46.069, abs=0.01)
    assert 0 <= ev.payload["qed"] <= 1


def test_invalid_smiles_fails_at_structure_gate():
    run = MoleculeLab().run({"smiles": "C1(CC"})
    assert not run.passed
    assert run.first_loss.rule_id == "MOL-STRUCT-002"


def test_calculation_failure_after_preflight_does_not_leave_a_false_pass():
    class FailsAfterStructureGate:
        engine_name = "rdkit-test-double"
        version = "test"

        def __init__(self):
            self.delegate = RDKitCalculator()
            self.calls = 0

        def calculate(self, smiles):
            self.calls += 1
            if self.calls == 1:
                return self.delegate.calculate(smiles)
            raise RDKitUnavailableError("backend disappeared after structural validation")

    run = MoleculeLab(calculator=FailsAfterStructureGate()).run({"smiles": "CCO"})

    assert not run.passed
    assert run.lifecycle == RunLifecycle.INDETERMINATE
    assert run.first_loss.rule_id == "MOL-CALC-001"
    assert run.first_loss.status == GateStatus.INDETERMINATE
    assert run.evidence == []


def test_morgan_features_are_ml_representation_not_property_calculation():
    fp = MorganFeaturizer().transform_one("CCO")
    assert fp.shape == (2048,)
    assert set(fp.tolist()).issubset({0, 1})


def test_ledger_is_immutable_per_run(tmp_path):
    run = MoleculeLab().run({"smiles": "CCO"})
    target = ProofEngine().write_ledger(run, tmp_path)
    payload = json.loads((target / "manifest.json").read_text())
    assert payload["run_id"] == run.run_id
    assert payload["digest"]
    with pytest.raises(FileExistsError):
        ProofEngine().write_ledger(run, tmp_path)
