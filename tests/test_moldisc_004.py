from __future__ import annotations

from pathlib import Path

import pytest

from research_os.molecular_discovery.aqsoldb_coverage import AqSolDBSourceRecord
from research_os.molecular_discovery.moldisc004 import (
    PROGRAM_ID,
    load_program_config_v4,
    run_moldisc_004,
    verify_measured_anchor,
)
from research_os.molecular_discovery.solubility import SolubilityPrediction


CONFIG = Path("programs/moldisc-004-nct-measured-anchor/program.json")


class FakePredictor:
    model_identity = "fake-frozen-esol-model"

    def evidence_manifest(self):
        return {
            "training": {
                "dataset_hash": "6de39771743dc4f15b191cffc27e1e02eb474457cc841afda565f31aff198e85",
                "training_hash": "300ddc4981e1a9c2fb3735e598bcca89fb98a1cd4722cd58454e5d923781f00b",
            },
            "applicability_domain": {
                "threshold": 0.26684684684684684,
            },
        }

    def predict(self, smiles: str) -> SolubilityPrediction:
        return SolubilityPrediction(
            smiles=smiles,
            predicted_log_s_mol_l=0.25,
            max_training_tanimoto=0.50,
            applicability_threshold=0.26684684684684684,
            in_domain=True,
        )


def _records():
    return (
        AqSolDBSourceRecord(
            "E-468",
            "CN1CCCC1c1cccnc1",
            0.79,
            "SNICXCGAKADSCV-UHFFFAOYSA-N",
        ),
    )


def test_moldisc_004_protocol_freezes_selected_seed_anchor_and_predictor():
    config = load_program_config_v4(CONFIG)
    assert config["program_id"] == PROGRAM_ID
    assert config["parent_program"]["selected_case_id"] == "ATX-014"
    assert config["seed"]["pdb_id"] == "1P2Y"
    assert config["seed"]["chem_comp_id"] == "NCT"
    assert config["measured_anchor"]["source_id"] == "E-468"
    assert config["measured_anchor"]["expected_measured_log_s_mol_l"] == pytest.approx(0.79)
    assert config["predictor"]["model_change_allowed"] is False
    assert config["comparison"]["performance_threshold"] is None
    assert config["next_program_boundary"]["generation_in_v1"] is False
    assert config["next_program_boundary"]["docking_in_v1"] is False


def test_exact_aqsoldb_anchor_identity_is_verified():
    pytest.importorskip("rdkit")
    config = load_program_config_v4(CONFIG)
    anchor = verify_measured_anchor(config, _records())
    assert anchor.source_id == "E-468"
    assert anchor.canonical_smiles == "CN1CCCC1c1cccnc1"
    assert anchor.inchikey == "SNICXCGAKADSCV-UHFFFAOYSA-N"
    assert anchor.measured_log_s_mol_l == pytest.approx(0.79)


def test_moldisc_004_computes_descriptive_seed_error_without_tuning(tmp_path: Path):
    pytest.importorskip("rdkit")
    result = run_moldisc_004(
        config_path=CONFIG,
        output_root=tmp_path / "run",
        predictor=FakePredictor(),
        aqsoldb_records=_records(),
    )
    assert result.program_id == PROGRAM_ID
    assert result.assessment.chemistry_status == "PASS"
    assert result.assessment.solubility_status == "IN_DOMAIN"
    assert result.assessment.docking_status == "NOT_REQUESTED"
    assert result.calibration.measured_log_s_mol_l == pytest.approx(0.79)
    assert result.calibration.predicted_log_s_mol_l == pytest.approx(0.25)
    assert result.calibration.signed_error_predicted_minus_measured == pytest.approx(-0.54)
    assert result.calibration.absolute_error == pytest.approx(0.54)
    assert result.calibration.max_training_tanimoto == pytest.approx(0.50)
    assert result.calibration.predictor_model_identity == "fake-frozen-esol-model"
    assert len(result.program_scientific_hash) == 64
    assert (tmp_path / "run" / "program_manifest.json").is_file()
    assert (tmp_path / "run" / "assessment.json").is_file()
    assert (tmp_path / "run" / "program_report.md").is_file()
